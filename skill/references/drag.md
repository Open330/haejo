# Drag inside an observed macOS window

For window size changes, use `haejo resize <bundle-id> --helper
--window "Now Playing Overlay" --width 600 --height 360` (dimensions in points).
This first uses AXSize without activation or mouse input. If AXSize is unavailable
before any write, it sends one bottom-right resize stroke to the same window,
including borderless/nonactivating overlays, while allowing the expected size
change. It keeps the real pointer and foreground unchanged. It reports the
original/resulting geometry and `size_verified` only
after both accessibility and the window server show the requested size. A fixed
or app-constrained size reports `resize_unavailable` or `resize_not_verified`;
inspect the actual size before any further action. An older helper needs updating.
The resize grip must implement bottom-right resizing; a posted stroke alone is
not a successful size change. This does not establish why an app restores a
different position after relaunch.

Use `haejo drag <bundle-id> --helper --from X Y --to X Y` for a requested
single drag. Coordinates are **points relative to the observed window's top-left**,
including its titlebar; they are not screen coordinates or Retina pixels.
Choose coordinates from a current capture/geometry, not guessed screen positions.
`haejo capture <bundle-id> --helper --window 'Exact title' --output /tmp/window.png`
saves a private PNG and returns `pixel_to_point` scale factors. Inspect that image
and multiply image pixel coordinates by those factors before dragging. Use a new
output path for each capture; existing files are not overwritten.
Optional: `--window 'Exact title'` (required for multiple windows),
`--duration 0.6` (0.1–2 seconds), repeated `--via X Y` (up to 12 waypoints).

For background AppKit controls that ignore first-mouse input, use `--prepare`
before the stroke. This prepares the window without activating the app or moving
the person's cursor. A posted stroke is not proof of the receiving result:
inspect selection, slider value or the canvas change. `--json` adds the fresh
full observation/diagnostics; default output is compact. A partially dispatched
stroke is never automatically repeated; failed/cancelled strokes attempt to
release the button at the last dispatched position in the same receiving window.

For reuse, use a Flow `drag` step with a **Window selector**, params
`{"from":{"x":20,"y":40},"to":{"x":220,"y":80},"duration":0.6}`,
optional `via` points and an explicit receiving postcondition. Reobserve and
verify the effect before continuing. Use the normal session guide for Flow
framing; no extra approval is needed for an already-authorized temporary edit.

Requires the signed helper capabilities `action.drag` and `drag.window_bound`.
Owned on-screen normal and floating app windows (macOS layers 0 and 3) are
supported by window binding. Layer 3 alone is not a reason to abandon Haejo.
An older helper may reject it with `CG window ownership or visibility mismatch`;
update that helper and re-observe before another undispatched gesture.
The target is the uniquely observed app window; a floating/nonactivating panel
does not need keyboard focus. The app may be in front or in the background.
The helper sends a continuous left-button stroke to that window; it does not
activate apps, move the global pointer, or provide cross-app file dragging.
To move the real cursor itself (hover effects), use [hover](hover.md).
Finder file moves, browser HTML drag-and-drop, window moving/resizing and cross-app
drops need their own receiving tests; they are not established by this route.
If unsupported, report the specific operation rather than substituting clicks.

`drag_unavailable`: check that the signed helper advertises both capabilities,
the step selects a Window and has a receiving postcondition (not `unverified_ok`).
Update an older helper before retrying a gesture that was not started.
