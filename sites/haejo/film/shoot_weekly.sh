#!/usr/bin/env bash
# Shoot the film's plates: a weekly issue review done with the installed Haejo.
#
#   1. Direct use: the same Haejo calls an agent makes for "find the 5 most
#      discussed open bugs in vscode and put them in a meeting note", under one
#      task with a goal and a reason per call (they show in the Haejo app).
#   2. Activity: the Haejo window rendered over that task's own receipts.
#   3. Reuse: weekly-bugs (Safari: reload + read the top 5) and weekly-memo
#      (TextEdit: write the note) saved to the library, then replayed for
#      "next week" with no model calls.
#
# Only public GitHub pages are read (signed out); the notes are new files in
# the output folder. Safari's tab bar is cropped from the plates.
#
#   sites/haejo/film/shoot_weekly.sh OUT
#   .venv/bin/python sites/haejo/film/render.py --plates OUT/plates --out DIR --lang ko
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(mkdir -p "$1" && cd "$1" && pwd); F=$OUT/frames; P=$OUT/plates; mkdir -p "$F" "$P"
H=/Applications/Haejo.app/Contents/Resources/runtime/launcher/haejo
URL='https://github.com/microsoft/vscode/issues?q=is%3Aissue%20state%3Aopen%20label%3Abug%20sort%3Acomments-desc'
PAGE='Issues · microsoft/vscode · GitHub'
NOTE1=$OUT/weekly-issues-1110.txt; NOTE2=$OUT/weekly-issues-1117.txt

note_window() {  # open an empty owned note next to the Safari window
  osascript -e 'tell application "TextEdit" to close (every window whose name starts with "weekly-issues") saving no'
  : > "$1"; open -a TextEdit "$1"; sleep 2
  osascript -e "tell application \"TextEdit\" to set bounds of (first window whose name is \"$(basename "$1")\") to {1180, 60, 1820, 820}"
}
cap() {  # cap NAME NOTE: both windows; capture never overwrites, so names are unique
  "$H" capture com.apple.Safari --helper --window "$PAGE" --output "$F/$1-safari.png" >/dev/null || true
  "$H" capture com.apple.TextEdit --helper --window "$(basename "$2")" --output "$F/$1-textedit.png" >/dev/null
}
bug_args() {  # "done — 결과: bug1: …; bug2: …" -> -p bugN=… lines
  python3 - "$1" <<'EOF'
import re, sys
s = open(sys.argv[1]).read().split('결과: ', 1)[1].split('\n')[0].strip()
for part in re.split(r'; (?=bug\d: )', s): print(part.replace(': ', '=', 1))
EOF
}

osascript -e 'tell application "Safari"' -e 'close (every window whose name contains "microsoft/vscode")' \
  -e 'make new document with properties {URL:"about:blank"}' -e 'set bounds of front window to {60, 60, 1160, 820}' -e 'end tell'
note_window "$NOTE1"; cap 0 "$NOTE1"

# 1. Direct use, as an agent would call it.
"$H" open-url "$URL" --browser com.apple.Safari --helper --task new --goal "주간 이슈 점검" \
  --detail "vscode에서 댓글 많은 열린 버그 5개를 찾아서 회의 메모로 정리해줘" --why "댓글 많은 열린 버그 목록 열기" > "$OUT/a1.out" 2>&1
TASK=$(grep -o 't-[0-9a-f]*' "$OUT/a1.out" | head -1); echo "$TASK" > "$OUT/task.txt"; sleep 1; cap 1 "$NOTE1"
"$H" run "$HERE/read-top5.json" --helper --task "$TASK" --why "상위 5건 제목 읽기" > "$OUT/a2.out" 2>&1; cap 2 "$NOTE1"
args=(); while IFS= read -r l; do args+=(-p "$l"); done < <(bug_args "$OUT/a2.out")
"$H" run "$HERE/memo.json" --helper --document "$NOTE1" --yes --task "$TASK" --why "읽은 5건을 회의 메모에 정리" \
  -p "date=11월 10일" "${args[@]}" > "$OUT/a3.out" 2>&1 || true   # TextEdit edits end commit_unverified; the save verifies
cap 3 "$NOTE1"
"$H" activate com.apple.TextEdit --window "$(basename "$NOTE1")" --helper --task "$TASK" --why "저장하려고 메모 창을 앞으로" >/dev/null
"$H" replay textedit_save -p "document=$NOTE1" -p "name=$(basename "$NOTE1")" --helper --yes --task "$TASK" \
  --why "회의 메모 저장" --finish-task > "$OUT/a5.out" 2>&1; cap 4 "$NOTE1"

# 2. Activity window over this task's receipts.
L="$HOME/Library/Application Support/Haejo"; FX=$OUT/activity; mkdir -p "$FX/Logs" "$FX/Tasks"
grep -l "$TASK" "$L"/Logs/*.jsonl | while IFS= read -r f; do cp -p "$f" "$FX/Logs/"; done
cp -Rp "$L/Tasks/$TASK" "$FX/Tasks/"
/Applications/Haejo.app/Contents/MacOS/HaejoSetup --activity-snapshot "$OUT/act" --activity-fixture "$FX"

# 3. Save as Flows, then next week's replay.
"$H" flows save "$HERE/weekly-bugs.json" --force >/dev/null; "$H" flows save "$HERE/weekly-memo.json" --force >/dev/null
note_window "$NOTE2"; osascript -e 'tell application "Safari" to set index of (first window whose name contains "microsoft/vscode") to 1'
cap r0 "$NOTE2"
"$H" replay weekly-bugs --helper --timings > "$OUT/r1.out" 2>&1; cap r1 "$NOTE2"
args=(); while IFS= read -r l; do args+=(-p "$l"); done < <(bug_args "$OUT/r1.out")
"$H" replay weekly-memo --helper --document "$NOTE2" --yes --timings -p "date=11월 17일" "${args[@]}" > "$OUT/r2.out" 2>&1 || true
cap r2 "$NOTE2"
"$H" activate com.apple.TextEdit --window "$(basename "$NOTE2")" --helper >/dev/null
"$H" replay textedit_save -p "document=$NOTE2" -p "name=$(basename "$NOTE2")" --helper --yes > "$OUT/r3.out" 2>&1; cap r3 "$NOTE2"

# Plates: crop Safari's tab bar, keep TextEdit's text area.
for n in 1 r1; do ffmpeg -v error -y -i "$F/$n-safari.png" -filter_complex \
  "[0]crop=2200:100:0:0[a];[0]crop=2200:1340:0:180[b];[a][b]vstack" "$P/safari-$n.png"; done
for n in 0 3 4 r0 r2 r3; do ffmpeg -v error -y -i "$F/$n-textedit.png" -vf "crop=1280:420:0:0" "$P/textedit-$n.png"; done
cp "$OUT/act/app.png" "$P/activity.png"
python3 - "$OUT" <<'EOF'
import json, sys
out = sys.argv[1]
def timing(name):
    return next(json.loads(l.split(' ', 1)[1]) for l in open(f'{out}/{name}') if l.startswith('HAEJO_TIMINGS '))
a, b = timing('r1.out'), timing('r2.out')
json.dump({'replay_seconds': round(a['replay_seconds'] + b['replay_seconds'], 2), 'bugs_seconds': a['replay_seconds'],
           'memo_seconds': b['replay_seconds'], 'task': open(f'{out}/task.txt').read().strip()}, open(f'{out}/plates/facts.json', 'w'))
EOF
cat "$P/facts.json"
