#!/usr/bin/env bash
# Build and sign the haejo launcher — the only client the helper accepts.
set -euo pipefail
cd "$(dirname "$0")"
. ../signing.sh
SWIFTC=/Library/Developer/CommandLineTools/usr/bin/swiftc
SDK=$(/bin/ls -d /Library/Developer/CommandLineTools/SDKs/MacOSX*.sdk | /usr/bin/tail -1)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp haejo.swift "$STAGE/main.swift"
"$SWIFTC" -O -target "$HAEJO_SWIFT_TARGET" -sdk "$SDK" "$STAGE/main.swift" ../SigningPolicy.swift ../HelperModeProtocol.swift ../RuntimeStatus.swift HelperModeClient.swift -o "$STAGE/haejo"
haejo_select_identity
haejo_sign "$STAGE/haejo" "$HAEJO_LAUNCHER_ID"
haejo_warn_team_change haejo "$STAGE/haejo"
mv "$STAGE/haejo" haejo
echo "built and verified: $(pwd)/haejo"
