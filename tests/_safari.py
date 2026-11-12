"""Close the Safari tabs a native test opened, without bringing Safari forward."""
import subprocess

_CLOSE = '''
on run argv
  set origin to item 1 of argv
  if application "Safari" is not running then return -1
  tell application "Safari"
    repeat with wi from (count of windows) to 1 by -1
      try
        set w to window wi
        repeat with ti from (count of tabs of w) to 1 by -1
          try
            if (URL of tab ti of w) starts with origin then close tab ti of w
          end try
        end repeat
      end try
    end repeat
    set remaining to 0
    repeat with w in windows
      repeat with t in tabs of w
        try
          set u to URL of t
          if u is not missing value and u is not "" and u does not start with "favorites:" then set remaining to remaining + 1
        end try
      end repeat
    end repeat
    return remaining
  end tell
end run
'''


def running():
    return subprocess.run(['pgrep', '-xq', 'Safari']).returncode == 0


def close_origin(origin, quit_if_idle=False):
    """Close every tab under ``origin``; quit Safari when the test started it
    and no other page is open."""
    try:
        out = subprocess.run(['osascript', '-e', _CLOSE, origin.rstrip('/') + '/'],
                             capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return
    if quit_if_idle and out.stdout.strip() == '0':
        subprocess.run(['osascript', '-e', 'tell application "Safari" to quit'],
                       capture_output=True, timeout=20)


_OPEN = '''
on run argv
  tell application "Safari"
    make new document with properties {URL:item 1 of argv}
    delay 1
    set w to missing value
    repeat with candidate in windows
      try
        if (URL of current tab of candidate) is (item 1 of argv) then set w to candidate
      end try
    end repeat
    if w is missing value then return -1
    repeat with i from 2 to (count of argv)
      tell w to make new tab at end of tabs with properties {URL:item i of argv}
    end repeat
    return id of w
  end tell
end run
'''


def open_window(urls):
    """A new Safari window of its own for a test, one tab per URL, the first
    one showing; Safari stays behind the app in use. Returns the window ID."""
    out = subprocess.run(['osascript', '-e', _OPEN, *urls], capture_output=True, text=True, timeout=30)
    return int(out.stdout.strip() or -1)


def current_tab(window_id):
    """1-based place of the tab a window shows."""
    out = subprocess.run(['osascript', '-e',
                          f'tell application "Safari" to return index of current tab of window id {int(window_id)}'],
                         capture_output=True, text=True, timeout=20)
    return int(out.stdout.strip() or -1)
