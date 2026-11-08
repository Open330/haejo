# Pinned iOS transport probe

Read-only research tooling. It does not launch apps, pair devices, mount DDI,
install WDA/helper apps, read an AX tree or send input. The missing live AX bridge
and Python driver contract are described in [the spike design](../../docs/ios-spike.md).

```sh
cargo check --locked --manifest-path spike/ios-idevice/Cargo.toml
cargo run --locked --manifest-path spike/ios-idevice/Cargo.toml -- --capabilities
cargo run --locked --manifest-path spike/ios-idevice/Cargo.toml -- --list
```

`--capabilities` checks the compiled upstream HID type and explicitly reports
`ax_snapshot_implemented=false`, `tap_execution_enabled=false` and
`physical_validation=false`. `--list` only counts unique device identifiers and
transport connections from the default usbmux socket, with a five-second
discovery deadline. It does not print UDIDs,
pairing records or device names. Neither result proves that a phone is ready
for accessibility/input operations.

`upstream.json` records the exact MIT dependency revision and license digest.
Cargo.lock is supplied with the spike; build using `--locked`. No POKI source
is included. `target/` contains local build artifacts and is ignored.
