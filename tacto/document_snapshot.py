"""Compose existing native facts for a TextEdit Save As preparation.

Editing mode is a UI fact, not the disk source format. No method here writes,
authorizes Save, or certifies formatting/attachment fidelity.
"""
from copy import deepcopy
import hashlib
import re

from .flow import _same_role
from .document_label import window_flag

TARGET = 'com.apple.TextEdit'
CAPABILITY = 'evidence.document_snapshot'
REQUIRED = frozenset({
    'evidence.document_text', 'evidence.document_text.window_selector',
    'observe.document_token', 'evidence.document_mode', 'evidence.save_panel',
    'action.click.save_panel_guard', 'evidence.document_attachment_metadata',
    'evidence.save_panel.commit_selector',
})
PUBLIC_CODES = frozenset({
    'snapshot_body_unavailable', 'snapshot_source_unavailable',
    'snapshot_source_window_ambiguous', 'snapshot_source_selection_invalid',
    'snapshot_commit_selection_invalid', 'snapshot_backend_unavailable',
    'snapshot_attachment_read_unavailable', 'snapshot_attachment_not_supported',
    'snapshot_document_changed', 'snapshot_edited_state_invalid',
    'snapshot_save_panel_unavailable', 'snapshot_scoped_observation_unavailable',
    'snapshot_window_unavailable', 'snapshot_observation_incomplete',
    'snapshot_editing_mode_unavailable',
})


class SnapshotUnavailable(ValueError):
    """Closed error codes; never include native text, tokens or paths."""
    def __init__(self, code):
        self.public_code = code if type(code) is str and code in PUBLIC_CODES else 'snapshot_backend_unavailable'
        super().__init__(self.public_code)


def _window_index(tree, *, focused=False):
    """Read structural window indexes; this does not select an input action."""
    if not isinstance(tree, str):
        raise ValueError('invalid tree')
    matches = []
    for line in tree.splitlines():
        node = re.match(r'\s*(\d+)\s+(\w+)(?:\s|$)', line)
        if (node and _same_role(node[2], 'Window')
                and (not focused or window_flag(line, 'focused'))):
            matches.append(int(node[1]))
    if len(matches) != 1:
        raise ValueError('ambiguous window')
    return matches[0]


def _body(reply, token=None):
    if (not isinstance(reply, dict) or reply.get('type') != 'document_text'
            or not isinstance(reply.get('document_token'), str) or not reply['document_token']
            or len(reply['document_token']) > 128
            or token is not None and reply['document_token'] != token
            or not isinstance(reply.get('text'), str) or reply.get('text_complete') is not True
            or 'document_path' not in reply
            or reply['document_path'] is not None and not isinstance(reply['document_path'], str)):
        raise SnapshotUnavailable('snapshot_body_unavailable')
    return {key: reply[key] for key in ('document_token', 'text', 'document_path')}


class SnapshotDriver:
    def __init__(self, inner, *, source_window=None):
        """`source_window` is a host-selected (obs_id, window element index).

        Otherwise exactly one focused observed window must identify the source.
        The native mode reader independently binds its menu witness to that pin.
        """
        self._inner = inner
        self._source_window = source_window
        caps = frozenset(getattr(inner, 'capabilities', ()) or ())
        methods = ('document_text', 'document_mode', 'document_attachment_metadata', 'observe', 'save_panel')
        ready = REQUIRED <= caps and all(callable(getattr(inner, name, None)) for name in methods)
        self.capabilities = (caps - {CAPABILITY}) | ({CAPABILITY} if ready else set())

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _initial_selection(self):
        if self._source_window is not None:
            obs_id, index = self._source_window
        else:
            observation = self._inner.observe(TARGET, 'tree_full')
            if not isinstance(observation, dict) or observation.get('type') != 'observation':
                raise SnapshotUnavailable('snapshot_source_unavailable')
            try:
                index = _window_index(observation['tree'], focused=True)
            except (LookupError, ValueError, KeyError):
                raise SnapshotUnavailable('snapshot_source_window_ambiguous') from None
            obs_id = observation.get('obs_id')
        if not isinstance(obs_id, str) or not obs_id or type(index) is not int or index < 0:
            raise SnapshotUnavailable('snapshot_source_selection_invalid')
        return {'obs_id': obs_id, 'window_element_index': index}

    def document_snapshot(self, target, document_token=None):
        return self._snapshot(target, document_token)

    def document_snapshot_for_commit(self, target, *, document_token, event):
        """Read the current commit observation without replacing its element map."""
        action = event.get('action', {})
        if (not isinstance(document_token, str) or not document_token
                or not isinstance(event.get('obs_id'), str) or not event['obs_id']
                or not isinstance(action, dict) or set(action) != {'name', 'element_index'}
                or action['name'] != 'click' or type(action['element_index']) is not int
                or action['element_index'] < 0):
            raise SnapshotUnavailable('snapshot_commit_selection_invalid')
        return self._snapshot(target, document_token,
                              panel_selection=(event['obs_id'], action['element_index']))

    def _snapshot(self, target, document_token, *, panel_selection=None):
        if target != TARGET or CAPABILITY not in self.capabilities:
            raise SnapshotUnavailable('snapshot_backend_unavailable')
        options = self._initial_selection() if document_token is None else {'document_token': document_token}
        before = _body(self._inner.document_text(target, **options), document_token)
        token = before['document_token']
        attachments = self._inner.document_attachment_metadata(target, token)
        expected_hash = hashlib.sha256(before['text'].encode('utf-8')).hexdigest()
        if (not isinstance(attachments, dict) or attachments.get('type') != 'document_attachment_metadata'
                or attachments.get('document_token') != token
                or attachments.get('text_sha256') != expected_hash
                or attachments.get('document_path') != before['document_path']
                or attachments.get('sampled_stable') is not True
                or not isinstance(attachments.get('occurrences'), list)):
            raise SnapshotUnavailable('snapshot_attachment_read_unavailable')
        if any(not isinstance(row, dict) or row.get('ax_attachment_present') is not False
               for row in attachments['occurrences']):
            raise SnapshotUnavailable('snapshot_attachment_not_supported')
        observed = None
        if panel_selection is None:
            observed = self._inner.observe(target, 'tree_full', document_token=token)
        if panel_selection is not None:
            obs_id, commit_index = panel_selection
            panel = self._inner.save_panel(obs_id, target, commit_element_index=commit_index,
                                          document_token=token, require_format=True)
            mode = self._panel_mode(panel, token)
        else:
            panel, mode = self._observed_mode(target, token, observed)
        after = _body(self._inner.document_text(target, document_token=token), token)
        if before != after:
            raise SnapshotUnavailable('snapshot_document_changed')
        edited = mode.get('edited')
        if edited is not None and type(edited) is not bool:
            raise SnapshotUnavailable('snapshot_edited_state_invalid')
        return {'type': 'document_snapshot', **before, 'text_complete': True,
                'editing_mode': mode['editing_mode'], 'mode_witness': deepcopy(mode['witness']),
                'edited': edited, 'save_panel': deepcopy(panel), 'authorizes_save': False,
                'source_format_verified': False, 'attachment_fidelity_verified': False}

    @staticmethod
    def _panel_mode(panel, token):
        if (not isinstance(panel, dict) or panel.get('type') != 'save_panel'
                or panel.get('document_token') != token or panel.get('format') != 'rtf'
                or panel.get('authorizes_save') is not False):
            raise SnapshotUnavailable('snapshot_save_panel_unavailable')
        return {'editing_mode': 'rich_text', 'edited': None,
                'witness': {'source': 'save_panel_rtf', 'source_format_verified': False}}

    def _observed_mode(self, target, token, observed):
        if (not isinstance(observed, dict) or observed.get('type') != 'observation'
                or observed.get('document_token') != token or not isinstance(observed.get('tree'), str)
                or not isinstance(observed.get('obs_id'), str)):
            raise SnapshotUnavailable('snapshot_scoped_observation_unavailable')
        try:
            window = _window_index(observed['tree'])
        except (LookupError, ValueError):
            raise SnapshotUnavailable('snapshot_window_unavailable') from None
        sheets = any(len(parts := line.strip().split(maxsplit=2)) >= 2 and parts[0].isdigit()
                     and _same_role(parts[1], 'Sheet') for line in observed['tree'].splitlines())
        panel = None
        if sheets:
            panel = self._inner.save_panel(observed['obs_id'], target, window,
                                          document_token=token, require_format=True)
            mode = self._panel_mode(panel, token)
        else:
            if observed.get('truncated') is True:
                raise SnapshotUnavailable('snapshot_observation_incomplete')
            mode = self._inner.document_mode(target, document_token=token)
            if (not isinstance(mode, dict) or mode.get('type') != 'document_mode'
                    or mode.get('document_token') != token
                    or mode.get('editing_mode') not in ('rich_text', 'plain_text')
                    or not isinstance(mode.get('witness'), dict)
                    or mode['witness'].get('source') != 'format_menu'):
                raise SnapshotUnavailable('snapshot_editing_mode_unavailable')
        return panel, mode
