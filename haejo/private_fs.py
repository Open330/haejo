"""Product-private folders that the person's own later runs can always open."""
import os


def mkdir_private(folder, *, parents=False, exist_ok=False):
    """Create `folder` readable only by its user.

    POSIX gets mode 0o700. On Windows a mode makes Python (3.12.4 and later)
    write an owner-only ACL, and a folder first created from an elevated
    process (an administrator terminal, OpenSSH for an administrator) is owned
    by the Administrators group, which locks every later non-elevated run out
    of it. There the folder inherits the profile's own ACL instead, the same
    access every other app's data in the profile has (docs/windows.md).
    """
    if os.name == 'nt':
        folder.mkdir(parents=parents, exist_ok=exist_ok)
    else:
        folder.mkdir(mode=0o700, parents=parents, exist_ok=exist_ok)


def access_repair_hint(exc):
    """How to reopen a product folder an earlier elevated run locked, or ''.

    Folders Haejo created that way before mkdir_private kept an owner-only
    ACL owned by Administrators; only an administrator can give them back
    the profile's inherited access.
    """
    if os.name != 'nt' or not isinstance(exc, PermissionError):
        return ''
    from .preferences import product_directory
    folder = product_directory()
    return (f' {folder} 폴더에 접근할 수 없습니다. 관리자 권한으로 만들어진 폴더라면 관리자 터미널에서 '
            f'icacls "{folder}" /reset /t /c 를 한 번 실행하세요.')
