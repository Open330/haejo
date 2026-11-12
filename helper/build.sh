#!/usr/bin/env bash
# Build and sign the helper that holds the Accessibility grant.
#
# Swift only allows top-level statements in a file named main.swift, and the
# helper is split across several files now, so the entry point is staged under that
# name in a temp dir rather than renaming the source.
set -euo pipefail
cd "$(dirname "$0")"
. ../signing.sh
SWIFTC=/Library/Developer/CommandLineTools/usr/bin/swiftc
SDK=$(/bin/ls -d /Library/Developer/CommandLineTools/SDKs/MacOSX*.sdk | /usr/bin/tail -1)

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp HaejoHelper.swift "$STAGE/main.swift"
cp PeerAuth.swift  "$STAGE/PeerAuth.swift"
cp WindowInput.swift "$STAGE/WindowInput.swift"
cp PointerHover.swift "$STAGE/PointerHover.swift"
cp FrontmostProcess.swift "$STAGE/FrontmostProcess.swift"
cp SavePanelObservation.swift "$STAGE/SavePanelObservation.swift"
cp WindowDispatch.swift "$STAGE/WindowDispatch.swift"

SWIFT_ARGS=(-O -target "$HAEJO_SWIFT_TARGET" -sdk "$SDK" "$STAGE/main.swift" "$STAGE/PeerAuth.swift" "$STAGE/WindowInput.swift" "$STAGE/FrontmostProcess.swift" "$STAGE/SavePanelObservation.swift" "$STAGE/WindowDispatch.swift" "$STAGE/PointerHover.swift" "../SigningPolicy.swift" "../RuntimeStatus.swift" "../HelperModeProtocol.swift" "HelperModes.swift" "ParallelWindows.swift" "WebInput.swift" "TabFrontPointer.swift" "ApprovalClassifier.swift" "NativeApproval.swift" "NativeApprovalClient.swift" "NativeCommit.swift" -o "$STAGE/haejo-helper")
case "${HAEJO_ENABLE_EXPERIMENTAL_FOREGROUND:-0}" in
  0) ;;
  1)
    [ -f experimental/VroidDrag.swift ] || { echo 'Experimental foreground sources are unavailable in this checkout.' >&2; exit 2; }
    cp experimental/VroidDrag.swift "$STAGE/VroidDrag.swift"
    SWIFT_ARGS+=(-D HAEJO_EXPERIMENTAL_FOREGROUND "$STAGE/VroidDrag.swift")
    echo 'EXPERIMENTAL BUILD: VRoid foreground activation and global pointer input enabled.' >&2
    ;;
  *) echo 'HAEJO_ENABLE_EXPERIMENTAL_FOREGROUND must be 0 or 1.' >&2; exit 2 ;;
esac

"$SWIFTC" "${SWIFT_ARGS[@]}"

haejo_select_identity
haejo_sign "$STAGE/haejo-helper" "$HAEJO_HELPER_ID"
haejo_warn_team_change haejo-helper "$STAGE/haejo-helper"
mv "$STAGE/haejo-helper" haejo-helper
echo "built and verified: $(pwd)/haejo-helper"
