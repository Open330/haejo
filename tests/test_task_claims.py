"""Task claims on the cross-process leases, without screen access.

A small Swift program stands in for the helper: the real lease and claim
sources, with the screen front, the input wait and the task store replaced.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
import Foundation
import Darwin
// What the claim code reaches for in the helper.
func parallelRefusal(_ code: String) -> [String:Any] {
    ["type":"error","error":code,"effect":"not_started","retryable":code.hasSuffix("busy")]
}
final class ParallelWindowState {
    static let shared = ParallelWindowState()
    var requestTask: String?, requestDeadline: Double?, foregroundOwned = false
}
final class AbortStub { var isStopped = false }
let abortState = AbortStub()
nonisolated(unsafe) var frontPID: pid_t = 0
nonisolated(unsafe) var starts: [pid_t:Double] = [:]
nonisolated(unsafe) var returned: [pid_t] = []
func nativeFrontmostProcessPID() -> pid_t? { frontPID > 0 ? frontPID : nil }
func nativeProcessStartIdentity(_ pid: pid_t) -> Double? { starts[pid] }
func returnScreen(to previous: pid_t) -> Bool { returned.append(previous); frontPID = previous; return true }
func pid(forBundle bundle: String) -> pid_t? { Int32(bundle) }
func show(_ value: Any) { print(String(data: try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), encoding: .utf8)!); fflush(stdout) }

let args = CommandLine.arguments
let mode = args[1], scope = args[2]
func task(_ raw: String) -> String? { raw == "-" ? nil : raw }
if mode == "take" || mode == "hold" {
    // take <scope> <task|-> <act|read> <shared|exclusive> <ttl>
    HaejoScopeLease.claimSeconds = Int(args[6])!
    let lease = HaejoScopeLease()
    lease.task = task(args[3]); lease.acting = args[4] == "act"
    let ok = lease.take(scope, shared: args[5] == "shared")
    show(["ok": ok, "note": HaejoScopeLease.note(scope) ?? [:],
          "busy": busyRefusal("target_busy", scope, task: lease.task)])
    if mode == "hold" { var byte: UInt8 = 0; _ = read(0, &byte, 1) }
    withExtendedLifetime(lease) {}
} else if mode == "wait" {
    // wait <scope> <task|-> <act|read> <shared|exclusive> <seconds> <hold ms, or -1 for until stdin closes> [stale s]
    if args.count > 8 { HaejoWaitQueue.staleSeconds = Int(args[8])! }
    let lease = HaejoScopeLease()
    lease.task = task(args[3]); lease.acting = args[4] == "act"
    let began = ProcessInfo.processInfo.systemUptime
    let ok = waitForResource(lease, scope, shared: args[5] == "shared", deadline: began + Double(args[6])!)
    show(["ok": ok, "elapsed_ms": Int((ProcessInfo.processInfo.systemUptime - began) * 1000),
          "at_ms": Int(Date().timeIntervalSince1970 * 1000)])
    if ok, let hold = Int(args[7]) {
        if hold < 0 { var byte: UInt8 = 0; _ = read(0, &byte, 1) } else { usleep(UInt32(hold) * 1000) }
        show(["left_ms": Int(Date().timeIntervalSince1970 * 1000)])
    }
    withExtendedLifetime(lease) {}
} else if mode == "tickets" {
    show(["waiting": HaejoWaitQueue.waiting(scope), "tickets": HaejoWaitQueue.tickets(scope)])
} else if mode == "deadlines" {
    // Against a scope another process holds: which deadline ends the wait.
    func waited(_ deadline: Double?, request: Double?) -> Int {
        let began = ProcessInfo.processInfo.systemUptime
        ParallelWindowState.shared.requestDeadline = request.map { began + $0 }
        precondition(!waitForResource(HaejoScopeLease(), scope, deadline: deadline.map { began + $0 }))
        ParallelWindowState.shared.requestDeadline = nil
        return Int((ProcessInfo.processInfo.systemUptime - began) * 1000)
    }
    let raws: [Any?] = [nil, 30, 1, 120, 0.5, 121, true, "30", -1, 45.5]
    show(["caller": waited(0.3, request: nil), "request": waited(nil, request: 0.4),
          "earlier": waited(2, request: 0.2), "past": waited(-1, request: nil),
          "seconds": raws.map { leaseWaitSeconds($0) }, "tickets": HaejoWaitQueue.tickets(scope)])
} else if mode == "read-then-act" {
    // One connection reads under another task's claim, then acts.
    let lease = HaejoScopeLease()
    lease.task = task(args[3])
    let read = lease.take(scope)
    lease.acting = true
    let act = lease.take(scope)
    // The refused action gave the lock back: the claim's own task gets in.
    let owner = HaejoScopeLease()
    owner.task = task(args[4]); owner.acting = true
    let owned = owner.take(scope)
    withExtendedLifetime(owner) {}
    lease.task = nil
    show(["read": read, "act": act, "owner_act": owned, "untasked_act": lease.take(scope)])
} else if mode == "acting" {
    show([["type":"act","action":["name":"click"]], ["type":"act","action":["name":"read"]],
          ["type":"foreground_begin"], ["type":"tab_select"], ["type":"observe"], ["type":"capture"],
          ["type":"foreground_end"], ["type":"document_text"]].map { actingRequest($0) })
} else if mode == "front" {
    // The front token, with tasks opened and closed in memory.
    HaejoScopeLease.frontScope = scope
    var open: Set<String> = []
    HaejoScopeLease.taskOpen = { open.contains($0) }
    let a = "t-" + String(repeating: "a", count: 24), b = "t-" + String(repeating: "b", count: 24)
    let person: pid_t = 100, x: pid_t = 200, y: pid_t = 300, other: pid_t = 999
    starts = [person: 1.5, x: 2.5, y: 3.5, other: 4.5]
    var log: [String:Any] = [:]
    func raise(_ claim: FrontClaim?, _ pid: pid_t) { frontPID = pid; claim?.raised(bundle: String(pid)) }

    // A takes the front for X; B's request to take it waits and is told who and how long.
    open = [a, b]; frontPID = person
    var claim = FrontClaim(task: a, deadline: nil)
    precondition(claim != nil); raise(claim, x); claim = nil
    var note = HaejoScopeLease.note(scope)!
    precondition(note["task"] as? String == a && note["previous_front"] as? Int == 100 && note["raised"] as? Int == 200)
    let began = ProcessInfo.processInfo.systemUptime
    precondition(FrontClaim(task: b, deadline: began + 0.3) == nil)
    log["waited"] = ProcessInfo.processInfo.systemUptime - began >= 0.3
    log["busy"] = busyRefusal("input_busy", scope, task: b)
    precondition(frontPID == x)

    // The same task comes again: it passes, and the person's app stays the one to return to.
    claim = FrontClaim(task: a, deadline: nil)
    precondition(claim != nil); raise(claim, y); claim = nil
    note = HaejoScopeLease.note(scope)!
    precondition(note["previous_front"] as? Int == 100 && note["raised"] as? Int == 300)

    // Working in the raised app renews the claim; another app's call leaves it.
    let before = note["claim_until"] as! Int
    sleep(1)
    HaejoScopeLease.renew(scope, task: a) { $0["raised"] as? Int == 200 }
    precondition(HaejoScopeLease.note(scope)!["claim_until"] as? Int == before)
    HaejoScopeLease.renew(scope, task: b) { _ in true }
    precondition(HaejoScopeLease.note(scope)!["claim_until"] as? Int == before)
    HaejoScopeLease.renew(scope, task: a) { $0["raised"] as? Int == 300 }
    note = HaejoScopeLease.note(scope)!
    precondition(note["claim_until"] as! Int > before && note["previous_front"] as? Int == 100)

    // An open task keeps the front; a finished one gives it back while its app is still in front.
    precondition(releaseTaskFront(a)["front_returned"] as? Bool == false && returned.isEmpty)
    open = [b]
    precondition(releaseTaskFront(b)["front_returned"] as? Bool == false && returned.isEmpty)
    precondition(releaseTaskFront(a)["front_returned"] as? Bool == true)
    precondition(returned == [person] && frontPID == person)
    precondition(releaseTaskFront(a)["front_returned"] as? Bool == false && returned == [person])

    // The person moved to another app meanwhile: the screen stays as it is.
    open = [a, b]; returned = []; frontPID = person
    claim = FrontClaim(task: a, deadline: nil); raise(claim, x); claim = nil
    frontPID = other; open = [b]
    precondition(releaseTaskFront(a)["front_returned"] as? Bool == false && returned.isEmpty && frontPID == other)

    // A's claim ended with X still in front; B takes the front next and
    // inherits the person's app, which comes back when B finishes.
    open = [a, b]; frontPID = person
    claim = FrontClaim(task: a, deadline: nil); raise(claim, x); claim = nil
    open = [b]
    claim = FrontClaim(task: b, deadline: nil)
    precondition(claim != nil); raise(claim, y); claim = nil
    note = HaejoScopeLease.note(scope)!
    precondition(note["task"] as? String == b && note["previous_front"] as? Int == 100 && note["raised"] as? Int == 300)
    open = []
    precondition(releaseTaskFront(b)["front_returned"] as? Bool == true && returned == [person])

    // The app was already in front, or another process now has that pid: nothing to give back.
    open = [a]; returned = []; frontPID = x
    claim = FrontClaim(task: a, deadline: nil); raise(claim, x); claim = nil
    precondition(HaejoScopeLease.note(scope)!["raised"] == nil)
    open = []
    precondition(releaseTaskFront(a)["front_returned"] as? Bool == false)
    open = [a]; frontPID = person
    claim = FrontClaim(task: a, deadline: nil); raise(claim, x); claim = nil
    starts[person] = 9.5; open = []
    precondition(releaseTaskFront(a)["front_returned"] as? Bool == false && returned.isEmpty)
    show(log)
}
'''


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'), 'macOS Swift runtime')
class TaskClaimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        folder = Path(cls.folder.name)
        (folder/'main.swift').write_text(HARNESS)
        cls.binary = folder/'claims'
        built = subprocess.run(['swiftc', str(folder/'main.swift'), str(ROOT/'HelperModeProtocol.swift'),
                                str(ROOT/'helper/TaskClaims.swift'), '-o', str(cls.binary)],
                               capture_output=True, text=True, timeout=180)
        assert built.returncode == 0, built.stderr
        # The helper asks the task store under the home directory; this one is the test's own.
        cls.home = folder/'home'
        cls.tasks = cls.home/'Library/Application Support/Haejo/Tasks'
        cls.tasks.mkdir(parents=True)

    def setUp(self):
        from haejo import task
        self.task = task
        self.scope = 'test:' + uuid.uuid4().hex
        self.a = task.start('claim test a', root=self.tasks)['id']
        self.b = task.start('claim test b', root=self.tasks)['id']

    def run_harness(self, *args):
        done = subprocess.run([str(self.binary), *map(str, args)], capture_output=True, text=True, timeout=30,
                              env={'CFFIXED_USER_HOME': str(self.home), 'PATH': '/usr/bin:/bin'})
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout.splitlines()[0])

    def take(self, task, kind='act', *, shared=False, ttl=90, scope=None):
        return self.run_harness('take', scope or self.scope, task or '-', kind,
                                'shared' if shared else 'exclusive', ttl)

    def test_a_claim_lingers_after_its_command_and_names_its_task(self):
        first = self.take(self.a)
        self.assertTrue(first['ok'])
        self.assertEqual(self.a, first['note']['task'])
        second = self.take(self.b)                      # A's process is gone; its claim is not
        self.assertFalse(second['ok'])
        busy = second['busy']
        self.assertEqual(('target_busy', 'not_started', True), (busy['error'], busy['effect'], busy['retryable']))
        self.assertEqual(self.a, busy['holder_task'])
        self.assertTrue(80 <= busy['claim_expires_in'] <= 90, busy)
        self.assertEqual(busy['claim_expires_in'] * 1000, busy['retry_after_ms'])
        self.assertIn(self.a, busy['detail'])
        self.assertEqual(self.a, second['note']['task'])        # a refused request leaves the note
        self.assertFalse(self.take(self.b, shared=True)['ok'])   # a window worker's action too

    def test_reads_and_untasked_commands_pass_and_leave_the_claim(self):
        until = self.take(self.a)['note']['claim_until']
        for task, kind, shared in ((self.b, 'read', False), (self.b, 'read', True), (None, 'act', False),
                                   (None, 'read', False)):
            with self.subTest(task=task, kind=kind, shared=shared):
                passed = self.take(task, kind, shared=shared)
                self.assertTrue(passed['ok'])
                self.assertEqual((self.a, until), (passed['note']['task'], passed['note']['claim_until']))
                self.assertNotIn('holder_task', passed['busy'] if task is None else {})
        self.assertFalse(self.take(self.b)['ok'])

    def test_untasked_commands_set_no_claim(self):
        self.assertNotIn('task', self.take(None)['note'])
        self.assertTrue(self.take(self.b)['ok'])
        self.assertTrue(self.take(None)['ok'])

    def test_the_same_task_passes_and_renews(self):
        first = self.take(self.a)['note']['claim_until']
        time.sleep(1.1)
        again = self.take(self.a, 'read')
        self.assertTrue(again['ok'])
        self.assertGreater(again['note']['claim_until'], first)
        self.assertNotIn('holder_task', again['busy'])
        self.assertEqual(1000, again['busy']['retry_after_ms'])

    def test_a_claim_ends_after_its_ttl(self):
        self.assertTrue(self.take(self.a, ttl=2)['ok'])
        self.assertFalse(self.take(self.b, ttl=2)['ok'])
        time.sleep(2.2)
        taken = self.take(self.b, ttl=2)
        self.assertTrue(taken['ok'])
        self.assertEqual(self.b, taken['note']['task'])
        self.assertFalse(self.take(self.a, ttl=2)['ok'])       # and now it is B's

    def test_a_finished_task_frees_its_claims_at_once(self):
        self.assertTrue(self.take(self.a)['ok'])
        self.assertFalse(self.take(self.b)['ok'])
        self.task.end(self.a, 'done', root=self.tasks)
        taken = self.take(self.b)
        self.assertTrue(taken['ok'])
        self.assertEqual(self.b, taken['note']['task'])

    def test_a_task_the_store_does_not_know_holds_nothing(self):
        unknown = 't-' + uuid.uuid4().hex[:24]
        self.assertTrue(self.take(unknown)['ok'])
        self.assertTrue(self.take(self.b)['ok'])

    def test_one_connection_reads_under_a_claim_and_its_action_waits(self):
        self.take(self.a)
        self.assertEqual({'read': True, 'act': False, 'owner_act': True, 'untasked_act': False},
                         self.run_harness('read-then-act', self.scope, self.b, self.a))
        self.assertEqual(self.a, self.take(self.b, 'read')['note']['task'])

    def test_a_live_holder_is_busy_for_every_request_as_before(self):
        holder = subprocess.Popen([str(self.binary), 'hold', self.scope, '-', 'read', 'exclusive', '90'],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                  env={'CFFIXED_USER_HOME': str(self.home), 'PATH': '/usr/bin:/bin'})
        try:
            self.assertTrue(json.loads(holder.stdout.readline())['ok'])
            for task, kind in ((None, 'read'), (self.b, 'read'), (self.b, 'act')):
                refused = self.take(task, kind)
                self.assertFalse(refused['ok'])
                self.assertEqual(holder.pid, refused['busy']['holder_pid'])
                self.assertEqual(1000, refused['busy']['retry_after_ms'])
                self.assertNotIn('holder_task', refused['busy'])
        finally:
            holder.kill(); holder.communicate(timeout=10)

    # ---- bounded, fair waiting

    def spawn(self, *args):
        process = subprocess.Popen([str(self.binary), *map(str, args)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   text=True, env={'CFFIXED_USER_HOME': str(self.home), 'PATH': '/usr/bin:/bin'})
        self.addCleanup(self.reap, process)
        return process

    @staticmethod
    def reap(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)

    def holder(self, task=None, *, shared=False):
        process = self.spawn('hold', self.scope, task or '-', 'act', 'shared' if shared else 'exclusive', 90)
        self.assertTrue(json.loads(process.stdout.readline())['ok'])
        return process

    def waiter(self, task=None, kind='act', *, shared=False, seconds=20, hold=150, stale=None):
        """A process in line for the scope, started once the ones before it have their tickets."""
        expected = len(self.tickets()) + 1
        process = self.spawn('wait', self.scope, task or '-', kind, 'shared' if shared else 'exclusive', seconds, hold,
                             *(() if stale is None else (stale,)))
        deadline = time.monotonic() + 10
        while len(self.tickets()) < expected:
            self.assertLess(time.monotonic(), deadline, 'the waiter never took a ticket')
            time.sleep(0.02)
        return process

    def tickets(self):
        return self.run_harness('tickets', self.scope)['tickets']

    @staticmethod
    def got(process):
        return json.loads(process.stdout.readline())

    def test_an_uncontended_wait_takes_at_once_and_leaves_no_ticket(self):
        before = self.run_harness('tickets', self.scope)
        self.assertEqual({'waiting': False, 'tickets': []}, before)
        for task, shared in ((None, False), (self.a, False), (self.a, True)):
            taken = self.run_harness('wait', self.scope, task or '-', 'act', 'shared' if shared else 'exclusive', 5, 0)
            self.assertTrue(taken['ok'])
            self.assertLess(taken['elapsed_ms'], 100)
            self.assertEqual(before, self.run_harness('tickets', self.scope))

    def test_the_wait_ends_at_the_callers_deadline(self):
        self.holder()
        report = self.run_harness('deadlines', self.scope)
        self.assertTrue(300 <= report['caller'] < 900, report)
        self.assertTrue(400 <= report['request'] < 1000, report)
        self.assertTrue(200 <= report['earlier'] < 800, report)
        self.assertLess(report['past'], 200)                      # one try, then busy
        self.assertEqual([10, 30, 1, 120, 10, 10, 10, 10, 10, 45.5], report['seconds'])
        self.assertEqual([], report['tickets'])                   # a waiter that gave up left the line

    def test_waiters_get_the_scope_in_the_order_they_came(self):
        for round in range(3):
            with self.subTest(round=round):
                self.scope = 'test:' + uuid.uuid4().hex
                holder = self.holder()
                waiters = [self.waiter(hold=120) for _ in range(4)]
                self.assertEqual([1, 2, 3, 4], [row[0] for row in self.tickets()])
                self.reap(holder)
                took = [self.got(process) for process in waiters]
                left = [self.got(process)['left_ms'] for process in waiters]
                self.assertTrue(all(row['ok'] for row in took), took)
                times = [row['at_ms'] for row in took]
                self.assertEqual(sorted(times), times)
                for earlier, later in zip(left, times[1:]):       # each got it after the one before left
                    self.assertLessEqual(earlier, later)
                for process in waiters:
                    process.wait(timeout=10)
                self.assertEqual({'waiting': False, 'tickets': []}, self.run_harness('tickets', self.scope))

    def test_a_dead_waiters_ticket_is_skipped(self):
        holder = self.holder()
        first, second = self.waiter(), self.waiter(hold=0)
        first.kill(); first.wait(timeout=10)                       # its ticket stays in the file
        began = time.monotonic()
        self.reap(holder)
        self.assertTrue(self.got(second)['ok'])
        self.assertLess(time.monotonic() - began, 1.5)

    def test_a_stopped_waiters_ticket_goes_stale_and_it_rejoins_when_it_runs_again(self):
        import os, signal
        holder = self.holder()
        first, second = self.waiter(hold=0, stale=1), self.waiter(hold=300, stale=1)
        os.kill(first.pid, signal.SIGSTOP)
        try:
            self.reap(holder)
            self.assertTrue(self.got(second)['ok'])                # after the first ticket's 1 s ran out
        finally:
            os.kill(first.pid, signal.SIGCONT)
        self.assertTrue(self.got(first)['ok'])

    def test_later_shared_waiters_stay_behind_an_exclusive_one(self):
        reader = self.holder(shared=True)
        writer = self.waiter(hold=300)                             # exclusive, behind the reader
        late = self.waiter(shared=True, hold=0)                    # could share with the reader; waits its turn
        time.sleep(0.3)
        self.assertEqual(3 - 1, len(self.tickets()))               # both still in line
        self.reap(reader)
        wrote = self.got(writer)
        self.assertTrue(wrote['ok'])
        self.assertGreaterEqual(self.got(late)['at_ms'], self.got(writer)['left_ms'])

    def test_shared_waiters_go_together(self):
        holder = self.holder()
        readers = [self.waiter(shared=True, hold=-1) for _ in range(3)]
        self.reap(holder)
        self.assertTrue(all(self.got(reader)['ok'] for reader in readers))   # all three hold it at once

    def test_a_waiter_for_a_claim_stands_only_before_requests_the_claim_turns_away(self):
        c = self.task.start('claim test c', root=self.tasks)['id']
        self.assertTrue(self.take(self.a)['ok'])                   # A's claim; its process is gone
        second = self.waiter(self.b, hold=200)
        third = self.waiter(c, hold=0)
        for task, kind in ((None, 'act'), (self.b, 'read'), (self.a, 'act')):
            with self.subTest(task=task, kind=kind):               # a read, an untasked command and A itself pass
                passed = self.run_harness('wait', self.scope, task or '-', kind, 'exclusive', 5, 0)
                self.assertTrue(passed['ok'])
                self.assertLess(passed['elapsed_ms'], 500)
        self.assertEqual(2, len(self.tickets()))
        self.task.end(self.a, 'done', root=self.tasks)             # the claim ends: B, the older waiter, gets it
        self.assertTrue(self.got(second)['ok'])
        left = self.got(second)['left_ms']
        time.sleep(0.3)
        self.assertEqual(1, len(self.tickets()))                   # C now waits for B's claim
        self.task.end(self.b, 'done', root=self.tasks)
        self.assertGreaterEqual(self.got(third)['at_ms'], left)
        third.wait(timeout=10)
        self.assertEqual(c, self.take(c, 'read')['note']['task'])

    def test_acting_requests(self):
        self.assertEqual([True, False, True, True, False, False, False, False],
                         self.run_harness('acting', self.scope))

    def test_front_token_waits_for_another_task_and_gives_the_screen_back(self):
        report = self.run_harness('front', 'front-test:' + uuid.uuid4().hex)
        self.assertTrue(report['waited'])
        busy = report['busy']
        self.assertEqual('input_busy', busy['error'])
        self.assertEqual('t-' + 'a' * 24, busy['holder_task'])
        self.assertEqual(busy['claim_expires_in'] * 1000, busy['retry_after_ms'])


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swift'), 'macOS Swift required')
class LauncherTaskIdentityTests(unittest.TestCase):
    def test_launcher_allows_validated_task_identity_and_lease_wait_on_target_requests(self):
        source = (ROOT/'launcher/haejo.swift').read_text()
        schema = source[source.index('let allowedTypes:'):source.index('// MARK: - Socket plumbing')]
        checks = r'''
let task = "t-0123456789abcdef01234567", invocation = String(repeating:"a", count:32)
let observe: [String:Any] = ["type":"observe","target":"com.example.app"]
func with(_ base: [String:Any], _ extra: [String:Any]) -> [String:Any] { base.merging(extra) { _, new in new } }
let requests: [[String:Any]] = [
    with(observe, ["task_id":task,"invocation_id":invocation]),
    with(observe, ["task_id":task]),
    with(["type":"foreground_begin","target":"com.example.app"], ["task_id":task,"invocation_id":invocation]),
    with(["type":"foreground_end","target":"com.example.app"], ["task_id":task,"invocation_id":invocation]),
    with(["type":"window_list","target":"com.example.app"], ["task_id":task,"invocation_id":invocation]),
    ["type":"task_release","task_id":task],
    observe,
    with(observe, ["task_id":"t-short"]),
    with(observe, ["task_id":task,"invocation_id":"x"]),
    with(observe, ["invocation_id":invocation]),
    with(observe, ["task_id":7]),
    ["type":"ping","task_id":task],
    ["type":"release_targets","task_id":task],
    ["type":"task_release"],
    ["type":"task_release","task_id":task,"target":"com.example.app"],
    ["type":"task_release","task_id":task,"invocation_id":invocation],
    // lease_wait_seconds: 1...120 on a request that names a target.
    with(observe, ["lease_wait_seconds":60]),
    with(observe, ["lease_wait_seconds":1,"task_id":task,"invocation_id":invocation]),
    with(["type":"foreground_begin","target":"com.example.app"], ["lease_wait_seconds":120]),
    with(observe, ["lease_wait_seconds":121]),
    with(observe, ["lease_wait_seconds":0]),
    with(observe, ["lease_wait_seconds":true]),
    with(observe, ["lease_wait_seconds":"60"]),
    ["type":"ping","lease_wait_seconds":60],
    ["type":"release_targets","lease_wait_seconds":60],
]
print(String(data:try! JSONSerialization.data(withJSONObject:requests.map{vetted($0)==nil}),encoding:.utf8)!)
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'main.swift'
            path.write_text('import Foundation\nimport CoreFoundation\nfunc modelTimeout(_ raw:Any?)->Double? {1}\n'+schema+checks)
            result = subprocess.run(['swift', str(path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([True]*7 + [False]*9 + [True]*3 + [False]*6, json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
