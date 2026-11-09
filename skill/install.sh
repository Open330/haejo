#!/usr/bin/env bash
# Install Haejo for coding agents: the signed command on PATH and the skill.
#
#   skill/install.sh           install (or repair) both
#   skill/install.sh --check   say what is installed and what is missing; change nothing
#
# Two things used to go wrong. This script copied SKILL.md and nothing else,
# so an agent read "run `haejo apps`" and found no `haejo` anywhere (reported from a
# Codex session, 2026-09-28). And the copies went stale: every installed copy
# still described the skill as it was on 2026-09-17. Now the command is a link
# to the signed launcher, and the skill is a link to this directory, so what an
# agent reads is always what this checkout says.
set -euo pipefail

skill_dir=$(cd "$(dirname "$0")" && pwd -P)
repo=$(cd "$skill_dir/.." && pwd -P)
skill="$repo/skill"
bin_dir="${HAEJO_BIN_DIR:-$HOME/.local/bin}"
check=0
explicit_dirs=()
record=""
repair_record=""
usage() { echo 'usage: skill/install.sh [--check] [--bin-dir /absolute/bin] [--skill-dir /absolute/skills ...] [--record /new/record.json] [--repair-from /record.json]'; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check) [ "$check" = 0 ] || { usage >&2; exit 2; }; check=1; shift ;;
    --bin-dir|--skill-dir|--record|--repair-from)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$2" in /*) ;; *) usage >&2; exit 2 ;; esac
      case "$1" in
        --bin-dir) bin_dir="$2" ;;
        --skill-dir) explicit_dirs+=("$2") ;;
        --record) record="$2" ;;
        --repair-from) repair_record="$2" ;;
      esac
      shift 2 ;;
    --help) [ "$#" = 1 ] || { usage >&2; exit 2; }; usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
status=0
if [ -n "$record" ]; then
  if [ "$check" = 1 ] || [ ! -d "$(dirname "$record")" ] || [ ! -x "$repo/.venv/bin/python" ]; then
    echo '--record requires installation, an existing parent directory and runtime Python' >&2; exit 2
  fi
  if ! "$repo/.venv/bin/python" -I -B -c 'import haejo.install_record' >/dev/null 2>&1; then
    echo 'install record support unavailable in this runtime' >&2; exit 2
  fi
fi
if [ -n "$record" ] && { [ -e "$record" ] || [ -L "$record" ]; }; then
  say_record_error='not replacing existing install record'
  echo "$say_record_error" >&2; exit 2
fi
record_authorizes() {
  [ -n "$repair_record" ] && [ -x "$repo/.venv/bin/python" ] || return 1
  "$repo/.venv/bin/python" -I -B -m haejo.install_record authorize \
    --record "$repair_record" --root "$repo" --link "$1" --kind "$2"
}

say() { printf '  %s\n' "$*"; }
ours() {   # is this path an owned Haejo skill we may replace?
  record_authorizes "$1" skill && return 0
  [ "$(readlink "$1" 2>/dev/null)" = "$skill" ] && return 0
  [ -f "$1/SKILL.md" ] && grep -Eq '^name: haejo$' "$1/SKILL.md"
}
our_command_link() {
  record_authorizes "$1" command && return 0
  local old old_repo
  old=$(readlink "$1" 2>/dev/null) || return 1
  case "$old" in
    "$repo/launcher/haejo"|"$repo/.venv/bin/haejo") return 0 ;;
    /*/launcher/haejo) old_repo=${old%/launcher/haejo} ;;
    /*/.venv/bin/haejo) old_repo=${old%/.venv/bin/haejo} ;;
    *) return 1 ;;
  esac
  [ -f "$old_repo/skill/SKILL.md" ] && grep -Eq '^name: haejo$' "$old_repo/skill/SKILL.md"
}

echo "Haejo — $repo"

# A launcher link alone is not an agent installation. Refuse incomplete or
# incorrectly packaged checkouts before creating command/profile directories.
# This checks discoverable instructions, not signing or runtime permissions.
if [ ! -f "$skill/SKILL.md" ] || [ ! -r "$skill/SKILL.md" ] ||
   ! grep -Eq '^name: haejo$' "$skill/SKILL.md"; then
  say "missing or invalid: skill/SKILL.md — restore the Haejo skill from this checkout before installing"
  exit 1
fi

# 1. The command. The signed launcher is the entry point that holds the
#    permission boundary and works from any directory. A Python console script
#    cannot replace that boundary, even when it has the same command name.
entry=""
if [ -x "$repo/launcher/haejo" ]; then
  entry="$repo/launcher/haejo"
fi
target="$bin_dir/haejo"
echo "command"
if [ -z "$entry" ]; then
  say "missing: launcher/haejo — build the native checkout first:"
  say "  uv sync && ./build.sh"
  exit 1
elif [ $check = 1 ]; then
  if [ "$(readlink "$target" 2>/dev/null)" = "$entry" ]; then say "ok: $target -> $entry"
  else say "missing or conflicting: $target (would link to $entry)"; status=1; fi
else
  mkdir -p "$bin_dir"
  if { [ -e "$target" ] || [ -L "$target" ]; } && ! our_command_link "$target"; then
    say "not replacing $target: it is not our command link"
    exit 1
  fi
  ln -sfn "$entry" "$target"
  say "linked: $target -> $entry"
fi
# Retirement only: never install or execute a removed command name.
# nlc: the first name. tacto: the name before Haejo (2026-11-09). A tacto link is ours
# when it points at this checkout's former launcher/tacto or .venv/bin/tacto.
retired_link_ours() {
  our_command_link "$1" && return 0
  case "$(readlink "$1" 2>/dev/null)" in
    "$repo/launcher/$2"|"$repo/.venv/bin/$2") return 0 ;;
  esac
  return 1
}
for retired_name in nlc tacto; do
  retired_command="$bin_dir/$retired_name"
  if [ -L "$retired_command" ] && retired_link_ours "$retired_command" "$retired_name"; then
    if [ "$check" = 1 ]; then
      say "retired command link needs removal: $retired_command"; status=1
    else
      rm -- "$retired_command"
      say "removed retired command link: $retired_command"
    fi
  fi
done
case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) say "warning: $bin_dir is not on PATH — add it, or agents will not find haejo" ;;
esac

# 2. The skill, everywhere an agent reads skills: the default Claude Code and
#    Codex homes, the active ones if relocated, and asx profiles.
echo "skill"
if [ "${#explicit_dirs[@]}" -gt 0 ]; then
  dirs=("${explicit_dirs[@]}")
else
  dirs=("$HOME/.claude/skills" "$HOME/.codex/skills")
  [ -n "${CLAUDE_CONFIG_DIR:-}" ] && dirs+=("$CLAUDE_CONFIG_DIR/skills")
  [ -n "${CODEX_HOME:-}" ] && dirs+=("$CODEX_HOME/skills")
  for d in "$HOME/Library/Application Support/asx/profiles"/*/skills; do
    [ -d "$d" ] && dirs+=("$d")
  done
fi
seen=""
for parent in "${dirs[@]}"; do
  if [ ! -d "$parent" ]; then
    if [ $check = 1 ]; then
      say "missing: $parent/haejo"; status=1; continue
    fi
    mkdir -p "$parent"
  fi
  real=$(cd "$parent" && pwd -P)
  case "$seen" in *"|$real|"*) continue ;; esac
  seen="$seen|$real|"
  dest="$parent/haejo"
  for retired_name in nlc tacto; do
    retired_skill="$parent/$retired_name"
    if [ -L "$retired_skill" ] && ours "$retired_skill"; then
      if [ "$check" = 1 ]; then
        say "retired skill link needs removal: $retired_skill"; status=1
      else
        rm -- "$retired_skill"
        say "removed retired skill link: $retired_skill"
      fi
    fi
  done
  if [ $check = 1 ]; then
    if [ "$(readlink "$dest" 2>/dev/null)" = "$skill" ]; then say "ok: $dest"
    elif [ -e "$dest" ] || [ -L "$dest" ]; then say "stale copy or conflicting link: $dest"; status=1
    else say "missing: $dest"; status=1; fi
    continue
  fi
  if { [ -e "$dest" ] || [ -L "$dest" ]; } && ! ours "$dest"; then
    say "not replacing $dest: it is not the Haejo skill"
    if [ -L "$dest" ] && [ ! -e "$dest" ]; then
      say "link target is missing; verify the previous Haejo checkout before replacing this link"
    fi
    status=1
    continue
  fi
  if [ -L "$dest" ]; then
    ln -sfn "$skill" "$dest"
  else
    if [ -e "$dest" ]; then
      # Keep old SKILL.md outside the discovery root to avoid duplicate skills.
      backup=$(mktemp -d "$(dirname "$parent")/.haejo-skill-backup.XXXXXX")
      mv "$dest" "$backup/haejo"
      say "kept previous copy: $backup/haejo"
    fi
    ln -s "$skill" "$dest"
  fi
  say "linked: $dest"

done
if [ "$status" = 0 ] && [ "$check" = 0 ] && [ -n "$record" ]; then
  record_args=()
  for parent in "${dirs[@]}"; do record_args+=(--skill-link "$parent/haejo"); done
  if ! "$repo/.venv/bin/python" -I -B -m haejo.install_record write \
      --record "$record" --root "$repo" --link "$target" "${record_args[@]}"; then
    say "links installed, but install record could not be written"; status=1
  fi
fi
exit "$status"
