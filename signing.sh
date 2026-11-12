# Native peers trust the same Apple-issued signing team, not one developer team.
HAEJO_LAUNCHER_ID=ai.callabo.haejo
HAEJO_HELPER_ID=ai.callabo.haejo.helper
# The oldest macOS every native binary and bundle is built for. One value for
# the compiler target and each Info.plist; setup/build_standalone_preview.py
# reads this line, so the floor never follows the build Mac's own version.
HAEJO_MACOS_TARGET=27.0
HAEJO_SWIFT_TARGET="$(/usr/bin/uname -m)-apple-macos$HAEJO_MACOS_TARGET"

haejo_select_identity() {
  if [ -n "${HAEJO_SIGN_IDENTITY:-}" ]; then
    IDENTITY=$HAEJO_SIGN_IDENTITY
  else
    # Prefer certificates meant for signing executables: Developer ID, then
    # Apple Development. Distribution certificates sign store submissions and
    # often need an interactive key prompt that a terminal session cannot show.
    local valid
    valid=$(security find-identity -p codesigning -v | grep -v CSSMERR)
    IDENTITY=$( { printf '%s\n' "$valid" | grep '"Developer ID Application:'; printf '%s\n' "$valid" | grep '"Apple Development:'; printf '%s\n' "$valid"; } \
      | sed -nE 's/^[[:space:]]*[0-9]+\) ([0-9A-Fa-f]{40}) .*/\1/p' | head -1)
  fi
  [ -n "$IDENTITY" ] && [ "$IDENTITY" != '-' ] || {
    echo 'An Apple-issued code signing identity is required; set HAEJO_SIGN_IDENTITY.' >&2
    return 1
  }
}

haejo_requirement() {
  local identifier=$1 team=$2
  [[ "$identifier" =~ ^[a-zA-Z0-9.-]+$ && "$team" =~ ^[A-Z0-9]{10}$ ]] || {
    echo 'Invalid signing identifier or team.' >&2; return 1;
  }
  printf 'identifier "%s" and anchor apple generic and certificate leaf[subject.OU] = "%s"' "$identifier" "$team"
}

haejo_sign() {
  local target=$1 identifier=$2 metadata team requirement
  # First signature discovers the actual certificate team. Never trust a team
  # supplied by the runtime environment or assume the certificate's CN format.
  codesign --force --sign "$IDENTITY" --identifier "$identifier" \
    --options runtime --timestamp=none "$target" || return
  metadata=$(codesign -dv --verbose=4 "$target" 2>&1) || return
  team=$(printf '%s\n' "$metadata" | sed -n 's/^TeamIdentifier=//p')
  requirement=$(haejo_requirement "$identifier" "$team") || return
  codesign --force --sign "$IDENTITY" --identifier "$identifier" \
    -r="designated => $requirement" --options runtime --timestamp=none "$target" || return
  codesign --verify --strict -R="$requirement" "$target" || return
  printf 'Verified signing team: %s (%s)\n' "$team" "$identifier"
}

# Warn before replacing a signed artifact whose designated identity changed.
# macOS permission grants bind to both the identifier and the signing team.
haejo_warn_team_change() {
  local previous=$1 replacement=$2 old new old_id new_id
  [ -e "$previous" ] || return 0
  old=$(codesign -dv --verbose=4 "$previous" 2>&1 | sed -n 's/^TeamIdentifier=//p') || return 0
  new=$(codesign -dv --verbose=4 "$replacement" 2>&1 | sed -n 's/^TeamIdentifier=//p') || return 0
  old_id=$(codesign -dv --verbose=4 "$previous" 2>&1 | sed -n 's/^Identifier=//p') || return 0
  new_id=$(codesign -dv --verbose=4 "$replacement" 2>&1 | sed -n 's/^Identifier=//p') || return 0
  if [ -n "$old" ] && [ "$old" != "$new" ]; then
    printf 'Signing team changed: %s -> %s. macOS permissions may need to be granted again. Set HAEJO_SIGN_IDENTITY to retain the intended team.\n' "$old" "$new" >&2
  fi
  if [ -n "$old_id" ] && [ "$old_id" != "$new_id" ]; then
    printf 'Signing identifier changed: %s -> %s. Grant macOS Accessibility and Screen Recording permissions to the new app identity.\n' "$old_id" "$new_id" >&2
  fi
}
