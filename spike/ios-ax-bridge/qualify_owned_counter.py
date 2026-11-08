"""Explicit development qualification, never a normal Tacto execution route.

The trusted host provides a private config for the owned counter and launch PID.
One durable marker is created before requesting input; reuse never starts a
second native worker. No ordinary/personal app or arbitrary coordinate API.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler

from tacto.ios_ax_probe import IOSAXProbe, IOSAXProbeError


class OwnedCounterProbe(IOSAXProbe):
    _expected_input_enabled = True


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def receiving_state(url):
    with build_opener(NoRedirect).open(url + 'state', timeout=3) as response:
        data = response.read(4097)
        if len(data) > 4096:
            raise ValueError('fixture_receiving_invalid')
        value = json.loads(data)
    if not isinstance(value, dict) or type(value.get('count')) is not int or value['count'] < 0:
        raise ValueError('fixture_receiving_invalid')
    return value


def validate_config(config):
    if set(config) != {'binary', 'device_id', 'expected_pid', 'fixture_url', 'fixture_heading'}:
        raise ValueError('fixture_config_invalid')
    parsed = urlsplit(config['fixture_url'])
    if (parsed.scheme != 'http' or not parsed.hostname or not parsed.port or parsed.query or parsed.fragment
            or parsed.username or not ipaddress.ip_address(parsed.hostname).is_private
            or not re.fullmatch(r'/[A-Za-z0-9_-]{32}/', parsed.path)
            or config['fixture_heading'] != 'Tacto test ' + parsed.path[1:9]
            or type(config['expected_pid']) is not int or config['expected_pid'] <= 0
            or not isinstance(config['binary'], str) or not Path(config['binary']).is_absolute()):
        raise ValueError('fixture_config_invalid')


def qualify(config, journal, *, simulate_reply_loss=False, prepare_only=False, probe_factory=OwnedCounterProbe,
            read_state=receiving_state):
    validate_config(config)
    journal = Path(journal)
    marker = journal / 'touch-requested.json'
    report = {'ok': False, 'physical_input_requested': False, 'receipts': [],
              'automatic_resume': False, 'promotion_allowed': False,
              'human_intervention_audited': False, 'prepare_only': prepare_only}
    if marker.exists():
        return {**report, 'error': 'fixture_input_unresolved_or_already_attempted'}
    probe = None
    try:
        if read_state(config['fixture_url'])['count'] != 0:
            raise ValueError('fixture_counter_not_zero')
        probe = probe_factory([config['binary'], '--owned-fixture'], config['device_id'],
                              transport='mobiledevice-lockdown', timeout=60)
        selectors = probe.capabilities()
        required = {'deviceInspectorMoveWithOptions:', 'deviceElement:valueForAttribute:'}
        if not required <= set(selectors):
            raise ValueError('fixture_ax_capabilities_missing')
        report['services'] = probe.service_readiness()['hid_transport_ping']
        report['preflight'] = probe._exchange({'command': 'prepare_owned_counter',
            'expected_pid': config['expected_pid'], 'fixture_heading': config['fixture_heading']})
        if (report['preflight'].get('counter') != 0
                or report['preflight'].get('target_pid_verified') is not True
                or report['preflight'].get('button_measured') is not True
                or report['preflight'].get('fixture_heading_seen') is not True
                or report['preflight'].get('current_orientation') != 'portrait'):
            raise ValueError('fixture_preflight_invalid')
        if prepare_only:
            report.update(ok=True, qualification_complete=False)
            return report
        if read_state(config['fixture_url'])['count'] != 0:
            raise ValueError('fixture_counter_changed_before_input')
        journal.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as output:
            json.dump({'state': 'requested_do_not_resend', 'fixture_sha256': hashlib.sha256(
                config['fixture_url'].encode()).hexdigest()}, output)
            output.flush()
            os.fsync(output.fileno())
        directory = os.open(journal, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        report['physical_input_requested'] = True
        report['receipts'] = [{'sent': None, 'screen_changed': None, 'screen_change_verified': False}]
        receipt = probe._exchange({'command': 'tap_owned_counter_once'})
        if simulate_reply_loss:
            # Discard the response at the host boundary. Leave the durable barrier intact.
            report.update(error='fixture_simulated_reply_loss', effect='unknown')
            return report
        report['receipts'][0].update({key: receipt.get(key) for key in
            ('sent', 'transport_ping', 'gesture_count', 'contact_reports', 'release_reports')})
        deadline = time.monotonic() + 4
        while True:
            state = read_state(config['fixture_url'])
            if state['count'] >= 1 or time.monotonic() >= deadline:
                break
            time.sleep(.1)
        if state['count'] != 1:
            report.update(error='fixture_receiving_unverified', effect='unknown', receiving=state)
            return report
        # Receiving progress is not AX progress; allow its bounded propagation before reading.
        time.sleep(.3)
        readback = probe._exchange({'command': 'read_owned_counter'})
        state = read_state(config['fixture_url'])
        report['receiving'] = state
        verified = (receipt.get('sent') is True and receipt.get('transport_ping') is True
                    and receipt.get('gesture_count') == 1 and readback.get('counter') == 1
                    and readback.get('ax_transition_verified') is True
                    and state['count'] == 1 and state.get('pointer_types') == ['touch'])
        report['receipts'][0].update(screen_changed=readback.get('counter') == 1,
                                     screen_change_verified=verified)
        report.update(ok=verified, qualification_complete=verified)
        if not verified:
            report.update(error='fixture_receiving_unverified', effect='unknown')
    except IOSAXProbeError as error:
        report.update(error=error.code, stage=error.stage, reason=error.reason)
        report['touch_attempted'] = error.touch_attempted
        if error.touch_attempted is False and report['receipts']:
            report['receipts'][0]['sent'] = False
        if error.mobiledevice_error_code is not None:
            report['mobiledevice_error_code'] = error.mobiledevice_error_code
        if error.observed_pid is not None:
            report['observed_pid'] = error.observed_pid
    except Exception:
        report['error'] = 'fixture_qualification_failed'
    finally:
        if probe is not None:
            probe.close()
        report['session_closed'] = probe is None or probe.closed
        if report['physical_input_requested'] and not report['ok']:
            report['effect'] = 'not_started' if report.get('touch_attempted') is False else 'unknown'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--simulate-reply-loss', action='store_true')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    result = qualify(json.loads(args.config.read_text()), args.journal,
        simulate_reply_loss=args.simulate_reply_loss, prepare_only=args.prepare_only)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['ok'] else 1)
