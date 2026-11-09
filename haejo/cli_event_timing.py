"""Bounded CLI event arrival times; not provider inference or native RPC timing."""
import json
import time


class CLIEventTiming:
    MAX_LINE_BYTES = 1024 * 1024
    MAX_EVENTS = 10000

    def __init__(self, *, clock=time.monotonic, start=None):
        self._clock = clock
        self._start = clock() if start is None else start
        self._buffer = bytearray()
        self._discarding = False
        self._events = []
        self._dropped = 0

    def feed(self, data):
        # Transport already bounds total output. Bound partial lines too and
        # discard oversized records until newline; never retain UI payloads.
        parts = data.split(b'\n')
        for index, part in enumerate(parts):
            complete = index < len(parts) - 1
            if not self._discarding:
                if len(self._buffer) + len(part) > self.MAX_LINE_BYTES:
                    self._buffer.clear()
                    self._discarding = True
                    self._dropped += 1
                else:
                    self._buffer.extend(part)
            if complete:
                if not self._discarding and self._buffer:
                    self._record(bytes(self._buffer))
                self._buffer.clear()
                self._discarding = False

    def _record(self, line):
        if len(self._events) >= self.MAX_EVENTS:
            self._dropped += 1
            return
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            self._dropped += 1
            return
        if not isinstance(event, dict):
            self._dropped += 1
            return
        kind = event.get('type')
        if kind not in {'thread.started', 'turn.started', 'turn.completed', 'turn.failed',
                        'item.started', 'item.updated', 'item.completed', 'error'}:
            return
        record = {'event': kind, 'received_seconds': round(max(0., self._clock() - self._start), 6)}
        item = event.get('item')
        if isinstance(item, dict):
            # IDs and item types are bounded protocol labels. Nothing from
            # command, arguments, output, reasoning or message is copied.
            for key in ('id', 'type'):
                value = item.get(key)
                if isinstance(value, str) and len(value) <= 256:
                    record['item_' + key] = value
        self._events.append(record)

    def phase_summary(self):
        """Host arrival intervals only; never label unobserved gaps inference."""
        events = self._events
        elapsed = max(0., self._clock() - self._start)
        pending, spans, unmatched = {}, [], 0
        for event in events:
            kind, key = event['event'], event.get('item_id')
            if event.get('item_type') not in ('command_execution', 'mcp_tool_call') or key is None:
                continue
            if kind == 'item.started':
                pending.setdefault(key, event['received_seconds'])
            elif kind == 'item.completed' and key in pending:
                spans.append((pending.pop(key), event['received_seconds']))
            elif kind == 'item.completed':
                unmatched += 1
        # Union overlapping tools so concurrent work is counted once.
        merged = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        active = sum(max(0., end - start) for start, end in merged)
        terminal = next((e['received_seconds'] for e in reversed(events)
                         if e['event'] in ('turn.completed', 'turn.failed')), None)
        return {'scope': 'host_event_arrival_intervals_not_inference_or_native_execution',
                'elapsed_seconds': round(elapsed, 6),
                'first_event_seconds': events[0]['received_seconds'] if events else None,
                'terminal_event_seconds': terminal,
                'completed_tool_spans': len(spans), 'unclosed_tool_spans': len(pending),
                'unmatched_tool_completions': unmatched,
                'tool_span_union_seconds': round(active, 6),
                'outside_completed_tool_spans_seconds': round(max(0., elapsed - active), 6),
                'complete': terminal is not None and not pending and not unmatched and self._dropped == 0 and not self._buffer}

    def snapshot(self):
        return {'schema': 'cli-event-arrival-timing-v1', 'clock': 'monotonic',
                'scope': 'host_received_stdout_events; transport_buffering_possible; not_inference_time',
                'events': [dict(event) for event in self._events],
                'phase_summary': self.phase_summary(),
                'dropped_records': self._dropped, 'partial_line_bytes': len(self._buffer)}
