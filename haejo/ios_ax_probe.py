"""Bounded development probe for the no-WDA AX service, without input capability.

This deliberately does not implement IOSSession: capabilities alone cannot
attest foreground identity, geometry, lock/modal state or authorized touch.
The trusted host supplies an executable argv and an explicit physical UDID.
"""
import json
import math
import os
import re
import select
import signal
import subprocess
import time


class IOSAXProbeError(ValueError):
    def __init__(self, code, *, stage=None, reason=None, observed_pid=None, touch_attempted=None, mobiledevice_error_code=None):
        super().__init__(code)
        self.code, self.stage, self.reason = code, stage, reason
        self.observed_pid = observed_pid
        self.touch_attempted = touch_attempted
        self.mobiledevice_error_code = mobiledevice_error_code


_STAGES = {'request', 'xcode_framework', 'coredevice_usage_assertion', 'usb_lockdown_service',
           'ax_service_socket', 'lockdown_shim_checkin', 'dtx_connection', 'ax_capabilities', 'ax_root',
           'fixture_services', 'fixture_display', 'fixture_hid', 'fixture_ping'}
_STAGES |= {'owned_counter_preflight', 'owned_counter_tap_preflight', 'owned_counter_dispatch', 'owned_counter_readback'}
_STAGES |= {'owned_counter_orientation', 'owned_counter_focus_first', 'owned_counter_pid',
            'owned_counter_find_heading', 'owned_counter_find_counter', 'owned_counter_find_button', 'owned_counter_measure'}
_REASONS = {'service_not_found', 'service_not_available', 'device_locked',
            'developer_mode', 'device_not_connected', 'device_connection_unavailable', 'coredevice_rejected',
            'mobiledevice_not_found', 'explicit_device_not_seen'}


class IOSAXProbe:
    """One process/connection, no transport fallback, retries or touch endpoint."""
    _expected_input_enabled = False
    def __init__(self, command, device_id, *, transport='coredevice-tunnel', timeout=50):
        if (not isinstance(command, (list, tuple)) or not command
                or any(not isinstance(part, str) or not part or '\0' in part for part in command)
                or not isinstance(device_id, str) or not re.fullmatch(r'[0-9a-fA-F-]{24,80}', device_id)
                or transport not in ('coredevice-tunnel', 'mobiledevice-lockdown')
                or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 60):
            raise IOSAXProbeError('ios_ax_probe_configuration_invalid')
        self.timeout, self.closed, self.connection_id = timeout, False, None
        environment = {key: os.environ[key] for key in ('HOME', 'TMPDIR', 'USER', 'LOGNAME', 'SSH_AUTH_SOCK')
                       if key in os.environ}
        environment.update(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0, start_new_session=True,
                                        env=environment)
        try:
            reply = self._exchange({'command': 'open', 'device_id': device_id, 'transport': transport})
            epoch = reply.get('connection_id')
            if (not isinstance(epoch, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', epoch)
                    or reply.get('transport') != transport):
                raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
            self.connection_id = epoch
            self.runtime_metadata = reply.get('xcode')
        except Exception:
            self.close()
            raise

    def _exchange(self, request):
        if self.closed:
            raise IOSAXProbeError('ios_ax_probe_closed')
        deadline = time.monotonic() + self.timeout
        try:
            pending = memoryview((json.dumps(request, separators=(',', ':')) + '\n').encode())
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                    raise IOSAXProbeError('ios_ax_probe_timeout')
                count = os.write(self.process.stdin.fileno(), pending)
                if count <= 0:
                    raise IOSAXProbeError('ios_ax_probe_disconnected')
                pending = pending[count:]
            data = bytearray()
            while b'\n' not in data:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                    raise IOSAXProbeError('ios_ax_probe_timeout')
                block = os.read(self.process.stdout.fileno(), 4096)
                if not block:
                    raise IOSAXProbeError('ios_ax_probe_disconnected')
                data.extend(block)
                if len(data) > 65536:
                    raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
            line, extra = data.split(b'\n', 1)
            if extra:
                raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
            reply = json.loads(line)
            if not isinstance(reply, dict) or type(reply.get('ok')) is not bool:
                raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
            if not reply['ok']:
                raise IOSAXProbeError('ios_ax_probe_failed',
                    stage=reply.get('stage') if reply.get('stage') in _STAGES else None,
                    reason=reply.get('reason') if reply.get('reason') in _REASONS else None,
                    observed_pid=reply.get('observed_pid') if type(reply.get('observed_pid')) is int and 0 < reply['observed_pid'] < 2**31 else None,
                    touch_attempted=reply.get('touch_attempted') if type(reply.get('touch_attempted')) is bool else None,
                    mobiledevice_error_code=reply.get('mobiledevice_error_code') if type(reply.get('mobiledevice_error_code')) is int else None)
            if reply.get('input_enabled') is not self._expected_input_enabled:
                raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
            return reply
        except IOSAXProbeError:
            self.close()
            raise
        except Exception:
            self.close()
            raise IOSAXProbeError('ios_ax_probe_protocol_invalid') from None

    def capabilities(self):
        reply = self._exchange({'command': 'capabilities'})
        selectors = reply.get('selectors')
        if (not isinstance(selectors, list) or len(selectors) > 512
                or any(not isinstance(item, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_:]{0,255}', item)
                       for item in selectors)):
            self.close()
            raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
        return tuple(selectors)

    def read_root(self):
        """One AX root/property query. No focus movement or complete-tree claim."""
        reply = self._exchange({'command': 'read_root'})
        if not isinstance(reply.get('root'), dict) or not isinstance(reply.get('attributes'), dict):
            self.close()
            raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
        return {'root': reply['root'], 'attributes': reply['attributes']}

    def service_readiness(self):
        """Read display metadata and PING a retained HID connection; no reports."""
        reply = self._exchange({'command': 'service_readiness'})
        if reply.get('hid_transport_ping') is not True or not isinstance(reply.get('display_info'), dict):
            self.close()
            raise IOSAXProbeError('ios_ax_probe_protocol_invalid')
        return {'hid_transport_ping': True, 'display_info': reply['display_info']}

    def close(self):
        if self.closed:
            return
        self.closed = True
        # EOF releases the native assertion. Bound shutdown even if a private call hangs.
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait()
        finally:
            self.process.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
