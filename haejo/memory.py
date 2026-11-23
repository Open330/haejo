"""One user-owned reference document shared by the skill and desktop app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from .preferences import product_directory
from .private_fs import mkdir_private
from .storage import write_private
from .task import _locked, _read_regular

MAX_BYTES = 32768


class MemoryStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else product_directory() / 'Memory'
        self.path = self.root / 'reference.md'

    def _check(self):
        if self.root.is_symlink() or self.root.parent.is_symlink():
            raise ValueError('메모리 폴더의 심볼릭 링크는 사용할 수 없습니다.')

    def read(self):
        self._check()
        try:
            data = _read_regular(self.path, MAX_BYTES)
        except FileNotFoundError:
            data = b''
        if len(data) > MAX_BYTES:
            raise ValueError('메모리는 UTF-8 32 KiB 이하여야 합니다.')
        return {'schema': 1, 'text': data.decode('utf-8'),
                'revision': hashlib.sha256(data).hexdigest(), 'path': str(self.path)}

    def replace(self, text, revision):
        if len(text.encode('utf-8')) > MAX_BYTES or '\0' in text:
            raise ValueError('메모리는 NUL 없이 UTF-8 32 KiB 이하여야 합니다.')
        self._check()
        mkdir_private(self.root, parents=True, exist_ok=True)
        with _locked(self.root):
            current = self.read()
            if revision != current['revision']:
                raise ValueError('메모리가 다른 곳에서 변경됐습니다. 새로고침한 뒤 변경 사항을 합쳐 주세요.')
            write_private(str(self.path), text)
            return self.read()


def main(argv=None, *, store=None):
    parser = argparse.ArgumentParser(prog='haejo memory', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('read', help='공통 메모리 읽기 (파일을 만들지 않음)')
    read.add_argument('--json', action='store_true')
    for name in ('set', 'clear'):
        command = commands.add_parser(name)
        command.add_argument('--revision', required=True, help='read --json의 revision')
        if name == 'set':
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument('--file', type=Path, help='UTF-8 문서')
            source.add_argument('--stdin', action='store_true', help='표준 입력에서 UTF-8 문서 읽기')
        command.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    store = store or MemoryStore()
    try:
        if args.command == 'read':
            result = store.read()
        else:
            text = ''
            if args.command == 'set':
                if args.stdin:
                    text = sys.stdin.read(MAX_BYTES + 1)
                else:
                    with args.file.open('rb') as stream:
                        text = stream.read(MAX_BYTES + 1).decode('utf-8')
            result = store.replace(text, args.revision)
        print(json.dumps(result, ensure_ascii=False) if args.json else result['text'], end='\n')
        return 0
    except (OSError, ValueError, UnicodeError) as exc:
        message = str(exc)
        print(json.dumps({'error': 'memory_unavailable', 'detail': message}, ensure_ascii=False)
              if args.json else message, file=sys.stdout if args.json else sys.stderr)
        return 2
