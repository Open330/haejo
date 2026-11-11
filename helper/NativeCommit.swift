// What a classified input would commit, read by the helper (stage 2, R7).
//
// The once-approval covers what the input commits, not the click:
//  * transmit / financial: the commit scope, the nearest container around the
//    control that holds both an editable field and a button (the composer, the
//    payment form). Everything in it is bound: body, recipients and chips,
//    attachments, amount, payee. The conversation above it, a typing
//    indicator or a clock are outside and do not void an answer.
//  * delete: the selected items (AX identity, index, URL, label) and the
//    window's document URL.
//  * credential: the page's site and the digest of the text being entered.
// The card shows a summary of the same reading; after "allowed" it is read
// again and must match exactly. Truncation and failed reads are part of it.
//
// Bounded: `maxNodes` elements and `budget` seconds for the whole reading;
// every AX call first lowers that element's messaging timeout to the time
// left, and stops when none is.

import Foundation
import ApplicationServices
import CommonCrypto

enum NativeCommit {
    static let maxNodes = 800, maxDepth = 14, maxList = 200, maxClimb = 8
    static let budget: TimeInterval = 0.5

    static let editableRoles: Set<String> = ["AXTextArea", "AXTextField", "AXComboBox"]
    static let buttonRoles: Set<String> = ["AXButton", "AXMenuButton", "AXLink"]
    static let recipientWords = ["to", "받는 사람", "받는사람", "수신", "宛先", "收件人", "recipient", "받는 분", "수취인", "payee", "cc", "bcc"]
    static let amountWords = ["amount", "금액", "송금액", "결제 금액", "이체 금액", "金額", "金额"]

    static func read(_ cls: ApprovalClass, anchor: AXUIElement?, pid: pid_t, payload: String?) -> CommitView {
        let window = anchor.flatMap(windowOf) ?? focusedWindow(pid)
        var walk = Walk(until: Date().addingTimeInterval(budget))
        var summary: [String: String] = [:]
        var unreadable: [String] = []
        if let window {
            switch cls {
            case .transmit, .financial:
                let scope = commitScope(from: anchor ?? window, window: window, walk: &walk)
                if scope.wholeWindow { unreadable.append("scope") }
                walk.reset(recordAll: true)
                walk.visit(scope.element, depth: 0)
            case .delete, .credential, .none:
                walk.reset(recordAll: false)              // selection, URLs, document only
                walk.visit(window, depth: 0)
            }
            if let document = walk.string(window, kAXDocumentAttribute as String) {
                walk.document = document
                walk.content.append(["document", document])
            }
        } else { walk.failed = true }
        let host = walk.urls.compactMap { URL(string: $0)?.host }.first ?? ""
        switch cls {
        case .transmit:
            let body = walk.fields.first { $0.role == "AXTextArea" && !$0.value.isEmpty }
                ?? walk.fields.first { !$0.isRecipient && !$0.value.isEmpty }
            if let body { summary["body"] = firstLine(body.value) } else { unreadable.append("body") }
            let recipients = walk.fields.filter { $0.isRecipient && !$0.value.isEmpty }.map(\.value)
            if !recipients.isEmpty { summary["recipient"] = String(recipients.joined(separator: ", ").prefix(80)) }
        case .delete:
            if !walk.selected.isEmpty {
                let names = walk.selected
                summary["items"] = "\(names.count): " + names.prefix(3).joined(separator: ", ") + (names.count > 3 ? " …" : "")
            } else if let document = walk.document {
                summary["items"] = URL(string: document)?.lastPathComponent ?? document
            } else { unreadable.append("items") }
        case .financial:
            // The amount field the person fills or sees as "amount" is the
            // amount; a price printed elsewhere is only shown as such.
            // Only a field labelled as the amount is shown as the amount; any
            // other money-looking value (a balance, a price) is only shown as
            // seen on screen, and the missing amount field is said.
            if let field = walk.fields.first(where: { $0.isAmount && !$0.value.isEmpty }) {
                summary["amount"] = field.value
            } else {
                let seen = walk.fields.map(\.value).filter(looksLikeAmount) + walk.texts.filter(looksLikeAmount)
                if !seen.isEmpty { summary["shown_amounts"] = seen.prefix(3).joined(separator: " · ") }
                unreadable.append(seen.isEmpty ? "amount" : "amount_field")
            }
            let payee = walk.fields.filter { $0.isRecipient && !$0.value.isEmpty }.map(\.value)
            if !payee.isEmpty { summary["recipient"] = String(payee.joined(separator: ", ").prefix(80)) }
            if host.isEmpty { unreadable.append("site") } else { summary["site"] = host }
        case .credential:
            if host.isEmpty { unreadable.append("site") } else { summary["site"] = host }
        case .none:
            break
        }
        if walk.truncated { unreadable.append("truncated") }
        if walk.failed { unreadable.append("failed") }
        var parts: [Any] = [cls.rawValue, host, walk.content, unreadable]
        if let payload { parts.append(digest([payload])) }
        return CommitView(digest: digest(parts), summary: summary, unreadable: unreadable, destination: host)
    }

    /// From the control up: the largest container that holds an editable
    /// field and a button but no history (a list, table, outline or a scroll
    /// area without an editable field: the conversation, the inbox). That is
    /// the composer or the payment form with its recipients and attachments,
    /// without the messages around it. The window when nothing qualifies.
    static func commitScope(from start: AXUIElement, window: AXUIElement, walk: inout Walk) -> (element: AXUIElement, wholeWindow: Bool) {
        var node = start
        var best: AXUIElement?
        // Complete only when the climb reaches the window with nothing that
        // might be history on the way. A list can be an attachment list as
        // well as a conversation; a stop there, at the climb limit or at the
        // budget is a boundary not established, and the card says so.
        var established = false
        for _ in 0...maxClimb {
            walk.reset(recordAll: true)
            walk.visit(node, depth: 0)
            if walk.truncated || walk.history > 0 { break }
            if !walk.fields.isEmpty && walk.buttons > 0 { best = node }
            // The window itself read with nothing that might be history: the
            // whole window is the composer, and that is complete.
            if CFEqual(node, window) { established = best != nil && CFEqual(best!, window); break }
            guard let parent = walk.element(node, kAXParentAttribute as String) else { break }
            node = parent
        }
        walk.truncated = false
        if let best { return (best, !established) }
        return (window, true)
    }

    static func firstLine(_ s: String) -> String {
        String(String(s.split(whereSeparator: \.isNewline).first ?? "").prefix(80))
    }

    /// Unambiguous: JSON of nested arrays, so no value can imitate a boundary.
    static func digest(_ parts: [Any]) -> String {
        let data = (try? JSONSerialization.data(withJSONObject: parts)) ?? Data()
        var hash = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        data.withUnsafeBytes { _ = CC_SHA256($0.baseAddress, CC_LONG(data.count), &hash) }
        return hash.map { String(format: "%02x", $0) }.joined()
    }

    static func looksLikeAmount(_ text: String) -> Bool {
        let t = text.trimmingCharacters(in: .whitespaces)
        guard t.count <= 40, t.contains(where: \.isNumber) else { return false }
        return t.contains(where: { $0.isCurrencySymbol }) || t.hasSuffix("원") || t.hasSuffix("円") || t.hasSuffix("元")
            || t.uppercased().hasPrefix("USD") || t.uppercased().hasPrefix("KRW")
    }

    static func windowOf(_ el: AXUIElement) -> AXUIElement? {
        if NativeApproval.string(el, kAXRoleAttribute as String) == kAXWindowRole as String { return el }
        return NativeApproval.element(el, kAXWindowAttribute as String)
    }
    static func focusedWindow(_ pid: pid_t) -> AXUIElement? {
        NativeApproval.element(AXUIElementCreateApplication(pid), kAXFocusedWindowAttribute as String)
    }

    struct Field { let role: String; let value: String; let isRecipient: Bool; let isAmount: Bool }

    struct Walk {
        let until: Date
        var recordAll = true
        var fields: [Field] = [], texts: [String] = [], selected: [String] = [], urls: [String] = []
        var buttons = 0
        /// Containers of history (messages, mail list) seen in this subtree.
        var history = 0
        var document: String?
        /// What the digest is taken over: one array per element read.
        var content: [[String]] = []
        var nodes = 0, truncated = false, failed = false

        init(until: Date) { self.until = until }

        /// Start a new reading of a subtree; the time budget and node count go on.
        mutating func reset(recordAll: Bool) {
            self.recordAll = recordAll
            fields = []; texts = []; selected = []; urls = []; buttons = 0; history = 0; content = []
        }

        /// Before every AX call: time left, and that element's timeout set to it.
        mutating func ready(_ el: AXUIElement) -> Bool {
            let left = until.timeIntervalSinceNow
            guard left > 0.01 else { truncated = true; return false }
            if AXUIElementSetMessagingTimeout(el, Float(left)) != .success { failed = true; return false }
            return true
        }
        mutating func copy(_ el: AXUIElement, _ name: String) -> CFTypeRef? {
            guard ready(el) else { return nil }
            var value: CFTypeRef?
            let error = AXUIElementCopyAttributeValue(el, name as CFString, &value)
            if error == .success { return value }
            if error != .noValue && error != .attributeUnsupported { failed = true }
            return nil
        }
        mutating func string(_ el: AXUIElement, _ name: String) -> String? {
            guard let v = copy(el, name) else { return nil }
            if let s = v as? String { return s }
            if let u = v as? URL { return u.absoluteString }
            return nil
        }
        mutating func element(_ el: AXUIElement, _ name: String) -> AXUIElement? {
            guard let v = copy(el, name), CFGetTypeID(v) == AXUIElementGetTypeID() else { return nil }
            return (v as! AXUIElement)
        }
        mutating func list(_ el: AXUIElement, _ name: String) -> [AXUIElement] {
            guard let all = copy(el, name) as? [AXUIElement] else { return [] }
            if all.count > NativeCommit.maxList { truncated = true }
            return Array(all.prefix(NativeCommit.maxList))
        }

        mutating func visit(_ el: AXUIElement, depth: Int) {
            guard depth <= NativeCommit.maxDepth, nodes < NativeCommit.maxNodes else { truncated = true; return }
            nodes += 1
            let role = string(el, kAXRoleAttribute as String) ?? ""
            let subrole = string(el, kAXSubroleAttribute as String) ?? ""
            let secure = subrole == "AXSecureTextField"
            let title = string(el, kAXTitleAttribute as String) ?? ""
            let description = string(el, kAXDescriptionAttribute as String) ?? ""
            let value = secure ? "" : (string(el, kAXValueAttribute as String) ?? "")
            if recordAll {
                content.append(["\(depth)", role, subrole, title, description, secure ? "<secure>" : value])
                if NativeCommit.editableRoles.contains(role), !secure, subrole != "AXSearchField" {
                    let label = (title + " " + description).lowercased()
                    let recipient = role != "AXTextArea" && NativeCommit.recipientWords.contains { word in
                        label.split(whereSeparator: { !$0.isLetter }).contains { $0 == word } || (word.count > 2 && label.contains(word)) }
                    let amount = NativeCommit.amountWords.contains { label.contains($0) }
                    fields.append(Field(role: role, value: value, isRecipient: recipient, isAmount: amount))
                }
                if NativeCommit.buttonRoles.contains(role) { buttons += 1 }
                if ["AXList", "AXTable", "AXOutline", "AXBrowser"].contains(role) { history += 1 }
                if role == "AXScrollArea", !containsEditable(el) { history += 1 }
                if role == "AXStaticText", !value.isEmpty { texts.append(value) }
            }
            if role == "AXWebArea", let url = string(el, "AXURL") {
                urls.append(url); content.append(["url", url])
            }
            if ["AXTable", "AXOutline", "AXList", "AXBrowser"].contains(role) {
                let rows = list(el, kAXSelectedRowsAttribute as String) + list(el, kAXSelectedChildrenAttribute as String)
                for row in rows { select(row) }
            }
            for child in list(el, kAXChildrenAttribute as String) {
                visit(child, depth: depth + 1)
                if until.timeIntervalSinceNow <= 0.01 || nodes >= NativeCommit.maxNodes { truncated = true; return }
            }
        }

        /// A scroll area that wraps a text area is the body, not history.
        mutating func containsEditable(_ el: AXUIElement) -> Bool {
            for child in list(el, kAXChildrenAttribute as String).prefix(4) {
                if NativeCommit.editableRoles.contains(string(child, kAXRoleAttribute as String) ?? "") { return true }
            }
            return false
        }

        /// A selected item: its identity (AX element, index, URL) and a label.
        mutating func select(_ row: AXUIElement) {
            let url = string(row, kAXURLAttribute as String) ?? ""
            let index = (copy(row, kAXIndexAttribute as String) as? NSNumber).map { "\($0.intValue)" } ?? "?"
            let label = rowLabel(row, depth: 0) ?? (url.isEmpty ? "?" : (URL(string: url)?.lastPathComponent ?? url))
            selected.append(label)
            content.append(["selected", "\(CFHash(row))", index, url, label])
        }
        /// The row's own title, or the first non-secure text within two levels.
        mutating func rowLabel(_ el: AXUIElement, depth: Int) -> String? {
            guard nodes < NativeCommit.maxNodes else { truncated = true; return nil }
            nodes += 1
            if string(el, kAXSubroleAttribute as String) == "AXSecureTextField" { return nil }
            for name in [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute] as [String] {
                if let s = string(el, name), !s.isEmpty, s.count <= 200 { return s }
            }
            guard depth < 2 else { return nil }
            for child in list(el, kAXChildrenAttribute as String).prefix(8) {
                if let s = rowLabel(child, depth: depth + 1) { return s }
            }
            return nil
        }
    }
}
