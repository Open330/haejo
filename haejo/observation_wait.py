"""Look past the first observation page while waiting for a result.

`wait_until` checks a predicate against a capped observation. A result that
appears past the cap (the 61st row) was never seen. When the caller says the
predicate is about what is *present* (containment, not a comparison with an
earlier full tree), the wait may also read the observation's explicit
continuation pages: no model call, no input, no extra sleep, within the
caller's own deadline. A predicate that compares trees must not use this: a
page is a fragment, and against a full "before" tree it looks like change.
"""
import time

# The most continuation pages read per poll. The same bound as a session's
# explicit observe_next requests.
MAX_WAIT_PAGES = 8


def match_in_pages(observe, target, predicate, first, *, deadline, document_token=None):
    """Read `first`'s continuation pages until `predicate(tree)` holds.

    Returns (matching page or None, pages read). Stops at the first failed
    page, a repeated cursor, MAX_WAIT_PAGES, or the deadline; never sleeps.
    The matching page is the driver's latest observation (its obs_id is
    current). A predicate exception propagates exactly as on the first page.
    """
    current, seen, pages = first, set(), 0
    while pages < MAX_WAIT_PAGES:
        cursor = current.get('next_observation_cursor') if isinstance(current, dict) else None
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            break
        if time.monotonic() >= deadline:
            break
        seen.add(cursor)
        options = {'continuation': cursor, '_settle_after_action': False}
        if document_token is not None:
            options['document_token'] = document_token
        try:
            page = observe(target, 'tree_full', **options)
        except Exception:
            break
        pages += 1
        if not isinstance(page, dict) or page.get('type') != 'observation' or not isinstance(page.get('tree'), str):
            break
        if predicate(page['tree']):
            return page, pages
        current = page
    return None, pages
