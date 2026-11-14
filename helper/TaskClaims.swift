import Foundation
import Darwin

// Task claims: what an open task keeps between its commands — the apps it
// works in (the note of each exclusive lease, HelperModeProtocol.swift) and
// the screen front it took. docs/parallel-execution.md, "Task claims".

/// How long a request stays in line for a resource when it names no time itself.
let defaultLeaseWaitSeconds=10.0
/// The wait a request asked for (`lease_wait_seconds`, 1...120), or the default.
func leaseWaitSeconds(_ raw:Any?) -> Double {
    guard let number=raw as? NSNumber,CFGetTypeID(number) != CFBooleanGetTypeID(),
          number.doubleValue.isFinite,(1...120).contains(number.doubleValue) else { return defaultLeaseWaitSeconds }
    return number.doubleValue
}
/// Take `scope` for `lease`, in line behind older waiters. The wait ends at
/// the earlier of the caller's `deadline` and the request's own deadline
/// (ParallelSession.respond: the request's `lease_wait_seconds`, 10 s unless it
/// says otherwise, and never past its input deadline); 10 s when neither is set.
func waitForResource(_ lease: HaejoScopeLease, _ scope: String, shared: Bool = false,
                     deadline: Double? = nil, cancelled: () -> Bool = { abortState.isStopped }) -> Bool {
    if scope=="global-input", ParallelWindowState.shared.foregroundOwned { return true }
    let until=[deadline,ParallelWindowState.shared.requestDeadline].compactMap { $0 }.min()
        ?? ProcessInfo.processInfo.systemUptime+defaultLeaseWaitSeconds
    return lease.wait(scope,shared:shared,until:until,cancelled:cancelled)
}
/// A busy refusal that names who has `scope` and when to come back: the live
/// holder process, and the task whose claim on it is still running.
func busyRefusal(_ code:String,_ scope:String,task:String?=ParallelWindowState.shared.requestTask) -> [String:Any] {
    var refusal=parallelRefusal(code)
    refusal["retry_after_ms"]=1000
    guard let holder=HaejoScopeLease.holder(scope) else { return refusal }
    refusal.merge(holder) { current,_ in current }
    if let owner=holder["holder_task"] as? String,let left=holder["claim_expires_in"] as? Int,task != nil,owner != task {
        refusal["retry_after_ms"]=left*1000
        refusal["detail"]="task \(owner) is working here; its claim lasts \(left) s more unless that task calls again, and ends at once when it finishes. Retry after retry_after_ms, or work in another app or window meanwhile"
    } else {
        // The lock itself is held: a claim is what keeps another task out.
        refusal["holder_task"]=nil;refusal["claim_expires_in"]=nil
        if code=="target_busy" {
            refusal["detail"]="another Haejo client holds this app; finish or end that command (an idle session holds it only until its flow arrives)"
        }
    }
    return refusal
}
/// Window claims under an app. A window worker holds its app shared, so the
/// app's own note says nothing about it. Each task-bound window worker lists
/// its window ID in the note of `window-claims:<pid>:<start>`; the claim itself
/// stays in the window's note. A request that takes the whole app for another
/// task looks the listed windows up, and a live claim on any of them counts as
/// a claim on the app. The list holds 16 window IDs; an ID whose claim has
/// ended leaves it the next time a worker lists a window.
enum WindowClaims {
    static let limit=16
    static func index(_ pid:pid_t,_ start:Double) -> String { "window-claims:\(pid):\(start)" }
    static func scope(_ pid:pid_t,_ start:Double,_ id:UInt32) -> String { "window:\(pid):\(start):\(id)" }
    private static func listed(_ note:[String:Any]?) -> [Int] { note?["windows"] as? [Int] ?? [] }
    /// `task`'s worker has window `id`: keep it in the app's list. While
    /// another task's claim on the whole app is live the window stays off the
    /// list, so that task goes on working; whoever claimed first keeps going.
    static func list(_ pid:pid_t,_ start:Double,_ id:UInt32,task:String) {
        let index=index(pid,start)
        if listed(HaejoScopeLease.note(index)).contains(Int(id)) { return }
        if let whole=HaejoScopeLease.liveClaim(HaejoScopeLease.note("app:\(pid)")),whole.task != task { return }
        HaejoScopeLease.edit(index) { note in
            var windows=listed(note).filter {
                $0 != Int(id) && HaejoScopeLease.liveClaim(HaejoScopeLease.note(scope(pid,start,UInt32($0)))) != nil
            }
            windows.append(Int(id))
            return ["windows":Array(windows.suffix(limit))]
        }
    }
    /// The window of this app that an open task other than `task` has a live
    /// claim on, and that claim.
    static func foreign(_ pid:pid_t,_ start:Double,task:String) -> (scope:String,claim:(task:String,left:Int))? {
        for id in listed(HaejoScopeLease.note(index(pid,start))) {
            let window=scope(pid,start,UInt32(id))
            if let claim=HaejoScopeLease.liveClaim(HaejoScopeLease.note(window)),claim.task != task { return (window,claim) }
        }
        return nil
    }
    /// For a request that takes the whole app `bundle` for `task`.
    static func foreign(bundle:String,task:String?) -> (scope:String,claim:(task:String,left:Int))? {
        guard let task,let pid=pid(forBundle:bundle),let start=nativeProcessStartIdentity(pid) else { return nil }
        return foreign(pid,start,task:task)
    }
}
/// A task's hold on the screen front. Taken, with the input lease already
/// held, wherever a task brings an app forward; its note keeps the app that
/// was in front before, which the end of the task gives back.
final class FrontClaim {
    private let lease=HaejoScopeLease()
    private var previous:pid_t=0
    /// nil while another open task's claim on the front is live. A nil
    /// `deadline` asks once; otherwise this waits as any resource does.
    init?(task:String,deadline:Double?,cancelled:()->Bool={ abortState.isStopped }) {
        lease.task=task;lease.acting=true
        guard deadline==nil ? lease.take(HaejoScopeLease.frontScope) : waitForResource(lease,HaejoScopeLease.frontScope,deadline:deadline,cancelled:cancelled)
        else { return nil }
        let front=nativeFrontmostProcessPID() ?? 0
        previous=front
        // The app in front is one a task raised and nothing gave back since:
        // the app before it is still the one to return to.
        if front>0,let old=lease.prior(HaejoScopeLease.frontScope),old["raised"] as? Int==Int(front),
           let before=old["previous_front"] as? Int,before>0,before != Int(front),
           old["task"] as? String==task
            || (old["claim_until"] as? Int ?? 0)>Int(Date().timeIntervalSince1970)-HaejoScopeLease.claimSeconds {
            previous=pid_t(before)
        }
        note(raised:nil)
    }
    private func note(raised:pid_t?) {
        var extra:[String:Any]=[:]
        if previous>0,let start=nativeProcessStartIdentity(previous) {
            extra["previous_front"]=Int(previous);extra["previous_start"]=start
            if let raised { extra["raised"]=Int(raised) }
        }
        lease.annotate(HaejoScopeLease.frontScope,extra)
    }
    /// The app this task left in front. Nothing is kept for giving back when
    /// that is the app that already was in front, or another app is.
    func raised(bundle:String) { raised(pid(forBundle:bundle)) }
    func raised(_ pid:pid_t?) {
        guard let pid,pid != previous,nativeFrontmostProcessPID()==pid else { previous=0;note(raised:nil);return }
        note(raised:pid)
    }
}
/// A task ended. The app that was in front before the task raised one comes
/// back, when the raised app is still in front: a person who has moved to
/// another app since keeps the screen as it is.
func releaseTaskFront(_ task:String) -> [String:Any] {
    let reply:[String:Any]=["type":"task_released","front_returned":false]
    guard !HaejoScopeLease.taskOpen(task),!abortState.isStopped,
          HaejoScopeLease.note(HaejoScopeLease.frontScope)?["task"] as? String==task else { return reply }
    let input=HaejoScopeLease(),lease=HaejoScopeLease()
    guard waitForResource(input,"global-input",deadline:ProcessInfo.processInfo.systemUptime+2),lease.take(HaejoScopeLease.frontScope),
          let note=lease.prior(HaejoScopeLease.frontScope),note["task"] as? String==task,
          let raised=note["raised"] as? Int,let previous=note["previous_front"] as? Int,raised>0,previous>0,
          let start=note["previous_start"] as? Double,nativeProcessStartIdentity(pid_t(previous))==start,
          nativeFrontmostProcessPID()==pid_t(raised) else { return reply }
    defer { withExtendedLifetime(input) {} }
    return reply.merging(["front_returned":returnScreen(to:pid_t(previous))]) { _,new in new }
}
/// Requests that change their target; everything else reads.
func actingRequest(_ msg:[String:Any]) -> Bool {
    switch msg["type"] as? String {
    case "foreground_begin","tab_select": return true
    case "act": return (msg["action"] as? [String:Any])?["name"] as? String != "read"
    default: return false
    }
}
