"""Clipboard snapshots for native paste tests (read only, never written)."""


def snapshot():
    from AppKit import NSPasteboard
    return [[(str(t), None if item.dataForType_(t) is None else bytes(item.dataForType_(t)))
             for t in item.types()]
            for item in NSPasteboard.generalPasteboard().pasteboardItems() or []]


def restored(before, after):
    """Every readable type is back with the same bytes and nothing new appeared.

    A type that had no data before (a conversion the system lists, such as the
    UTF-16 text WebKit copies advertise) may come back filled in, and types may
    come back in another order.
    """
    if len(before) != len(after):
        return False
    for old, new in zip(before, after):
        old, new = dict(old), dict(new)
        if not set(new) <= set(old):
            return False
        if any(new.get(t) != d for t, d in old.items() if d is not None):
            return False
    return True
