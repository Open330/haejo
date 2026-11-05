"""Host-owned continuation affordance; no native handle/cursor enters a prompt."""


def continuation_candidate(observation):
    cursor = observation.get('next_observation_cursor')
    if not isinstance(cursor, str) or not cursor:
        return None
    return {
        'element_index': -1,
        'role': 'ObservationPage',
        'label': '생략된 다음 관측 후보 보기',
        'match': '생략된 다음 관측 후보 보기',
        'attr': 'Title',
        'container': '',
        'where': '추가 관측 — 앱 조작 없음',
        'can': ['read'],
        'disabled': False,
        'line': '',
        '_observation_page': True,
    }
