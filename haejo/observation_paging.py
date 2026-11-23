"""Read-only views of an observation; native handles stay in the driver."""

import re
from dataclasses import dataclass

from .flow import Selector

_ELEMENT = re.compile(r"^(\s*)(\d+)\s+(\S+)")
_CONTAINERS = frozenset({
    'banner', 'cell', 'collection', 'complementary', 'contentinfo', 'dialog', 'form',
    'grid', 'group', 'list', 'listitem', 'main', 'menu', 'navigation', 'outline',
    'region', 'row', 'rowgroup', 'scrollarea', 'section', 'sheet', 'splitgroup',
    'tabgroup', 'table', 'tabpanel', 'toolbar', 'tree', 'treeitem', 'webarea', 'window',
})


@dataclass(frozen=True)
class ObservationRegion:
    index: int
    role: str
    label: str
    path: tuple[str, ...]
    lines: tuple[str, ...]
    indices: frozenset[int]
    name: str

    def summary(self):
        return dict(index=self.index, role=self.role, label=self.label,
                    path=self.path, element_count=len(self.indices))


def observation_regions(tree, *, candidate_indices=None, exact_name=None):
    """Find useful named branches within the current observation page."""
    lines = tree.splitlines()
    stack = []
    regions = []
    visible = []

    def close(end):
        _, index, role, label, ancestors, start, first = stack.pop()
        count = len(visible) - first
        if label and count >= 2:
            regions.append((index, role, label, ancestors, start, end, first, len(visible)))

    for position, line in enumerate(lines):
        node = _ELEMENT.match(line)
        if node is None:
            continue
        indent, index, role = len(node[1]), int(node[2]), node[3].rstrip(",")
        while stack and stack[-1][0] >= indent:
            close(position)
        label = ''
        ancestors = ()
        if role.lower().removeprefix('ax') in _CONTAINERS:
            label = (Selector._attr(line, 'Title') or Selector._attr(line, 'Description')
                     or Selector._stable_id(Selector._attr(line, 'Identifier') or ''))
            ancestors = tuple(item[3][:80] for item in stack if item[3])
        stack.append((indent, index, role, label, ancestors, position, len(visible)))
        if candidate_indices is None or index in candidate_indices:
            visible.append(index)
    while stack:
        close(len(lines))
    # A wrapper containing the same elements gives no additional place to look.
    spans = set()
    result = []
    for index, role, label, path, start, end, first, last in sorted(
            regions, key=lambda region: (len(region[3]), region[4])):
        span = (first, last)
        if exact_name is None:
            if span in spans or last - first == len(visible):
                continue
        elif label != exact_name:
            continue
        spans.add(span)
        result.append(ObservationRegion(index, role, label[:80], path[-3:],
                                        tuple(line for line in lines[start:end] if _ELEMENT.match(line)),
                                        frozenset(visible[first:last]), label))
        if len(result) == (12 if exact_name is None else 2):
            break
    return result


def observation_view(observation, *, regions=None, region=None):
    """Project a snapshot for display, leaving the driver's full tree intact."""
    view = {key: value for key, value in observation.items() if key != 'next_observation_cursor'}
    if observation.get('next_observation_cursor'):
        view['has_more_observation'] = True
    if regions:
        view = {key: view[key] for key in ('type', 'obs_id', 'target', 'truncated',
                'has_more_observation', 'element_count') if key in view}
        view.update(observation_view='overview', regions=[item.summary() for item in regions])
    elif region is not None:
        view.update(observation_view='region', region=region.summary(),
                    tree='\n'.join(region.lines), element_count=len(region.indices))
        for key in ('custom_selects', 'select_options'):
            if key in view:
                view[key] = {index: value for index, value in view[key].items()
                             if index.isdecimal() and int(index) in region.indices}
    return view


def region_candidates(regions, active_region):
    choices = {}
    if active_region is not None:
        choices[-1] = ('전체 관측 후보로 돌아가기', '추가 관측')
    for region in regions:
        if active_region is None or region.indices < active_region.indices:
            choices[region.index] = (region.label, ' / '.join((*region.path, region.role)))
    return {index: dict(element_index=index, role='ObservationRegion', label=label,
                        match=label, attr='Title', container='', where=where, can=['read'],
                        disabled=False, line='', _observation_region=True)
            for index, (label, where) in choices.items()}


def comparison_scope(observation):
    """Return a presentation baseline only for one complete visible scope."""
    if observation.get('truncated') or observation.get('next_observation_cursor'):
        return None
    lines = observation['tree'].splitlines()
    windows = [line for line in lines if (node := _ELEMENT.match(line))
               and node[3].rstrip(',').lower() in ('window', 'axwindow')]
    if len(windows) > 1:
        return None
    return (observation.get('url'), observation.get('document_token'),
            observation.get('document_id'), windows[0] if windows else next(iter(lines), ''))


def continuation_candidate(observation, *, reveal_supported=False):
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
        **({'_observation_reveal': True} if reveal_supported else {}),
    }
