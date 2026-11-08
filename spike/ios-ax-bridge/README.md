# Development iPhone AX and owned-counter qualification

This is a branch-only spike, not shipped iPhone execution. The default native
probe exposes explicit open, capabilities, root/property read, service readiness
and close. It reads no full AX tree, moves no focus and sends no touch reports.
`IOSAXProbe` refuses an input-enabled handshake and does not implement IOSSession.
The normal Tacto CLI still refuses iOS targets.

An explicit `--owned-fixture` native mode additionally permits a focus walk and
one gesture on the owned counter described below. It exposes no arbitrary
coordinate, selector, keyboard, clipboard or app-launch endpoint. The separate
`qualify_owned_counter.py` host must be used with trusted private configuration
and a durable journal. Nothing here installs/replaces Tacto or a phone app.

## Connection and licensing

The host selects an explicit UDID and either `mobiledevice-lockdown` (MobileDevice
secure service) or `coredevice-tunnel` (remote lockdown shim). The API name does
not prove USB hardware: qualify the actual discovery transport separately.
There is no first-device default, transport fallback, reconnect or direct
handshake with a second device RSD peer. AX service ownership and the HID
connection remain alive through receiving verification and cleanup.

The Python boundary has bounded calls/replies and kills a hung child. It strips
DYLD/DEVELOPER_DIR overrides; the native probe verifies Apple signatures before
loading Xcode/CoreDevice frameworks. CoreDevice usage assertions can bring up a
tunnel and keep a device awake; this is not an unchanged-power-state guarantee.
The local assertion adaptation accepts only actual fulfillment and rejects an
ended lease before/after socket allocation.

Fourteen vendored files originate from
[sunghyun-k/iphone-use at 6bf94902f1c30aac712ae594a9a3a08136157a48](https://github.com/sunghyun-k/iphone-use/tree/6bf94902f1c30aac712ae594a9a3a08136157a48),
under MIT. Thirteen are unchanged; `CoreDeviceClient.swift` has the documented
lease adaptation. `upstream.json` records paths, current hashes and the original
hash for that adaptation. `THIRD_PARTY_LICENSE.txt` retains the full notice.
The minimal gesture sender follows the same upstream report layout with that
notice retained. No POKI source is included. Private APIs require requalification
when Xcode/iOS changes; compilation is not physical qualification.

## Build and checks

```sh
swift build --package-path spike/ios-ax-bridge
TACTO_IOS_AX_PROBE="$PWD/spike/ios-ax-bridge/.build/debug/tacto-ios-ax-spike" \
  python -m unittest tests.test_ios_ax_probe_native
python -m unittest tests.test_ios_ax_probe tests.test_ios_counter_fixture \
  tests.test_ios_owned_counter tests.test_ios_gesture_native
```

Native protocol tests use invalid requests and never select hardware. Native
gesture tests compile the real sender with injected I/O, checking partial
contact, failed release, PING loss and refusal of a second gesture. These are
not physical fault-injection tests.

## Owned receiving fixture

```sh
python spike/ios-ax-bridge/counter_fixture.py --bind <explicit-reachable-host-IP>
```

The ephemeral HTTP server prints a random private URL; it does not navigate the
phone. It has no external assets, persistence or network retries. GET of its
`state` endpoint returns counts, sequences and browser-reported pointer types.
Duplicate requests are counted twice. Page-local sequences can repeat after
reload and are not deduplication keys. The heading includes a fresh nonce;
reload displays the current server count. Stop the server after the test.

The browser's trusted flag and pointer type cannot authenticate phone identity
or prove no person intervened. HTTP is plaintext on the chosen LAN interface;
keep the URL private. Receiving count alone is not attribution. Qualification
also needs the bound AX/PID/geometry evidence and a recorded input receipt.
Promotion is disabled and no human-intervention audit is claimed.

## Explicit qualification

The host privately creates a JSON config with exactly `binary` (absolute native
path), `device_id` (explicit UDID), `expected_pid` (the just-launched Safari PID),
`fixture_url` (this owned server's URL) and `fixture_heading` (its nonce heading).
Do not commit that config or raw AX/screenshot data. Launching Safari at the URL
is a separate authorized host step; the qualifier does not launch an app.

```sh
python spike/ios-ax-bridge/qualify_owned_counter.py \
  --config <private-config.json> --journal <persistent-run-directory> --prepare-only
python spike/ios-ax-bridge/qualify_owned_counter.py \
  --config <private-config.json> --journal <persistent-run-directory>
```

Prepare-only sends no touch and creates no dispatch marker. The input run
requires AX fixture heading, Counter 0 and button under the expected PID,
focus-box-measured geometry with a stable surrounding image, a fresh non-dark
screen, and current device orientation portrait with rot0 panel geometry.
Focus walking can scroll and change UI state; it is not a pure read.

Before input, the host creates and fsyncs an exclusive marker in the journal.
An existing marker refuses even a new worker. The native sender independently
permits only one gesture: two samples of the same contact and one release,
followed by HTTP/2 PING on the retained HID connection. On partial failure it
can attempt one release-only cleanup, never a new contact or connection.
PING proves transport progress, not a touch/application ACK.

The host polls receiving state with a deadline, then requires AX Counter 1,
HTTP count 1 and pointer types [touch]. A confirmed native pre-dispatch refusal
is not_started, and the marker still blocks reuse. Any uncertain write/reply
stays unknown, including with `--simulate-reply-loss`; there is no automatic
resume. That option discards a real response at the host boundary, so it can
still cause the one authorized fixture gesture and must not be run casually.

## Actual physical status: june-mba, 2026-11-06

MobileDevice lockdown read 45 AX capabilities and a root element Label.
DeviceHub View Screen brought the reported tunnel/DDI services online. Separate
CoreDevice deviceinfo and HID PING succeeded; current portrait orientation and
1179x2556 display geometry were read. CoreDevice AX shim failed independently.
The owned counter page was opened in Safari with its actual launch PID.

Prepare-only stopped on a focus PID mismatch; its cause is unresolved and the
check was not relaxed. A later service attempt failed, DeviceHub disappeared,
and the device became unavailable. No physical tap was sent. The independent
server count remained 0. The temporary server was stopped and no native worker
remained. Reconnect/unlock the phone, resolve the PID evidence, and complete
AX 0 -> one gesture -> AX/HTTP 1 plus physical failure tests before claiming
live iPhone execution. See docs/ios-spike.md and the validation record.
