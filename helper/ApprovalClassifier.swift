// Which inputs the signed helper itself treats as needing the person's answer
// when menu approval is enforced (docs: stage 2 design, S1).
//
// Pure and Foundation-only: the caller reads the element that will actually
// receive the input (resolved element, hit-tested point, focused element or
// resolved menu leaf) and passes what it saw. Nothing here comes from Python's
// safety declaration.
//
// The lexicon is narrow on purpose. A miss runs the input as today; a false
// match only adds a card, but a card in front of something the person already
// asked for is a delay, so ambiguous words ("order", "submit", "payment") are
// not in it.

import Foundation

enum ApprovalClass: String {
    case none, credential, financial, transmit, delete
}

/// What the helper observed about the input it is about to post.
struct ObservedInput: Equatable {
    /// Normalized input kind: "press" (click, double click, AXPress/AXConfirm,
    /// option/row press), "text" (set_value, type_text, paste), "return"
    /// (Return/Enter key or a newline in text), "key" (any other key), "menu"
    /// (resolved menu item leaf), "point" (hover/drag without a press).
    var kind: String
    var role: String = ""
    var subrole: String = ""
    /// Title, description, value of a button-like control; menu item title.
    var labels: [String] = []
    /// The element exposes AXPress (a group or cell the app made clickable).
    var pressable: Bool = false
    /// For "return": labels of the window's or sheet's AXDefaultButton, the
    /// control Return actually presses. Empty when there is none.
    var defaultButtonLabels: [String] = []
    /// For "return" in multi-line text: native evidence that Return runs the
    /// default action here instead of inserting a newline. Without it a
    /// text area's Return is a newline.
    var returnPressesDefault: Bool = false
    /// For "menu": the keyboard focus is in editable text (Edit > Delete then
    /// deletes text, not an item).
    var focusIsText: Bool = false
    /// Not used to classify: which element and window this is, so a card's
    /// answer is not spent on a different element with the same label.
    var identity: String = ""
    var window: String = ""
}

enum ApprovalClassifier {
    static let pressRoles: Set<String> = ["AXButton", "AXMenuItem", "AXLink", "AXMenuButton", "AXPopUpButton"]
    /// Toggles and navigation: pressing them changes a setting or a view.
    static let notCommitRoles: Set<String> = ["AXCheckBox", "AXRadioButton", "AXDisclosureTriangle", "AXTab",
                                              "AXSlider", "AXIncrementor", "AXColorWell"]

    static func classify(_ input: ObservedInput) -> ApprovalClass {
        switch input.kind {
        case "text":
            return input.subrole == "AXSecureTextField" ? .credential : .none
        case "return":
            // Return commits what the default button commits, whatever field
            // has focus (a password field's Return can be a Pay sheet's). With
            // no default button there is no evidence beyond a newline. A
            // multi-line text view inserts a newline (insertNewline:) unless
            // the helper has evidence otherwise.
            if input.role == "AXTextArea" && !input.returnPressesDefault { return .none }
            return strongest(input.defaultButtonLabels.map { classifyLabel($0, focusIsText: false) })
        case "press":
            guard !notCommitRoles.contains(input.role),
                  pressRoles.contains(input.role) || input.pressable else { return .none }
            return strongest(input.labels.map { classifyLabel($0, focusIsText: false) })
        case "menu":
            return strongest(input.labels.map { classifyLabel($0, focusIsText: input.focusIsText) })
        default:
            return .none
        }
    }

    /// Financial outranks delete outranks transmit: the card and the
    /// once-only rule follow the most serious reading.
    static func strongest(_ classes: [ApprovalClass]) -> ApprovalClass {
        for c in [ApprovalClass.financial, .delete, .transmit] where classes.contains(c) { return c }
        return .none
    }

    // MARK: lexicon

    /// English and other spaced languages: the first word is the verb.
    static let firstWord: [String: ApprovalClass] = [
        "send": .transmit, "post": .transmit, "publish": .transmit,
        "envoyer": .transmit, "senden": .transmit, "enviar": .transmit,
        "pay": .financial, "buy": .financial, "purchase": .financial, "checkout": .financial,
        "payer": .financial, "bezahlen": .financial, "pagar": .financial, "comprar": .financial,
        "delete": .delete, "erase": .delete, "supprimer": .delete, "löschen": .delete, "eliminar": .delete,
    ]
    /// Whole phrases whose first word alone is ambiguous.
    static let phrases: [String: ApprovalClass] = [
        "place order": .financial, "place your order": .financial, "complete purchase": .financial,
        "confirm payment": .financial, "check out": .financial, "submit order": .financial,
        "proceed to checkout": .financial, "confirm and pay": .financial,
        "move to trash": .delete, "move to bin": .delete, "empty trash": .delete, "empty bin": .delete,
        "permanently delete": .delete,
        "send money": .financial, "transfer money": .financial, "send payment": .financial,
        "make payment": .financial, "make a payment": .financial, "confirm purchase": .financial,
    ]
    /// A last word that turns a verb label into a place: "Purchase history",
    /// "Send settings", "Delete options".
    static let placeWords: Set<String> = ["history", "methods", "method", "settings", "options", "list",
                                          "details", "info", "preferences", "receipts", "status", "folder"]
    /// Languages written without spaces between verb and object: the label
    /// (spaces removed) ends with the verb phrase.
    static let endings: [(String, ApprovalClass)] = [
        ("결제하기", .financial), ("결제", .financial), ("구매하기", .financial), ("구매", .financial),
        ("주문하기", .financial), ("송금하기", .financial), ("송금", .financial), ("이체하기", .financial), ("이체", .financial),
        ("支払う", .financial), ("購入する", .financial), ("購入", .financial), ("注文を確定する", .financial), ("注文を確定", .financial),
        ("注文する", .financial), ("支付", .financial), ("购买", .financial), ("購買", .financial), ("付款", .financial),
        ("휴지통으로이동", .delete), ("삭제하기", .delete), ("삭제", .delete),
        ("削除する", .delete), ("削除", .delete), ("ゴミ箱に入れる", .delete), ("删除", .delete), ("刪除", .delete),
        ("移到废纸篓", .delete), ("移到垃圾桶", .delete),
        ("보내기", .transmit), ("전송하기", .transmit), ("전송", .transmit), ("게시하기", .transmit), ("게시", .transmit),
        ("送信する", .transmit), ("送信", .transmit), ("送る", .transmit), ("投稿する", .transmit), ("投稿", .transmit),
        ("发送", .transmit), ("發送", .transmit), ("发布", .transmit), ("發佈", .transmit),
    ]
    // Not here on purpose: "reply"/"답장" and "share" open a composer or a
    // sheet; the commit is the Send inside it.
    /// Labels that end with a verb above but name a setting or a list.
    static let notCommit: [String] = ["자동결제", "결제내역", "결제수단", "구매내역", "주문내역", "전송내역",
                                      "삭제된항목", "최근삭제된항목", "보낸편지함", "購入履歴", "支付方式",
                                      "결제설정", "전송설정", "購買紀錄", "购买记录"]
    /// Plain "Delete" in a text context edits text.
    static let textDelete: Set<String> = ["delete", "삭제", "削除", "删除", "supprimer", "löschen", "eliminar"]

    /// Compatibility-folded (full-width → ASCII), lower-cased, any Unicode
    /// space collapsed, trailing punctuation and a trailing price removed:
    /// "Pay\u{202f}$12.00" → "pay", "결제하기 ₩12,000" → "결제하기", "送信！" → "送信".
    static func normalize(_ label: String) -> String {
        let folded = label.precomposedStringWithCompatibilityMapping.lowercased()
        var words = folded.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        while let last = words.last, words.count > 1, isPrice(last) { words.removeLast() }
        var s = words.joined(separator: " ")
        while let c = s.last, c.isPunctuation || c == "…" { s.removeLast() }
        return s.trimmingCharacters(in: .whitespaces)
    }
    static func isPrice(_ word: String) -> Bool {
        let digits = word.filter(\.isNumber)
        guard !digits.isEmpty else { return false }
        let rest = word.filter { !$0.isNumber && !",.".contains($0) }
        return rest.allSatisfy { $0.isCurrencySymbol || "원円元".contains($0) }
    }

    static func classifyLabel(_ raw: String, focusIsText: Bool) -> ApprovalClass {
        let s = normalize(raw)
        guard !s.isEmpty, s.count <= 80 else { return .none }
        if focusIsText && textDelete.contains(s) { return .none }
        if let c = phrases[s] { return c }
        let words = s.split(separator: " ").map(String.init)
        if words.count > 1, let last = words.last, placeWords.contains(last) { return .none }
        let compact = s.replacingOccurrences(of: " ", with: "")
        if notCommit.contains(where: { compact.hasSuffix($0) || compact == $0 }) { return .none }
        for (ending, c) in endings where compact.hasSuffix(ending) { return c }
        if let first = words.first, let c = firstWord[first] { return c }
        return .none
    }
}
