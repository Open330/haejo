"""Every file the landing pages point at is in the repository.

The published site is the tracked content of sites/haejo/dist. A file that
exists only in a working folder (an ignored path, a forgotten `git add`)
passes local QA and is missing from the live page.
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT/'sites/haejo/dist'
REFERENCE = re.compile(r'''(?:src|href|poster|srcset)=["']([^"'#?]+)''')


def tracked():
    done = subprocess.run(['git', '-C', str(ROOT), 'ls-files', 'sites/haejo/dist'],
                          capture_output=True, text=True, timeout=30)
    return {ROOT/line for line in done.stdout.splitlines()} if done.returncode == 0 else None


class SiteAssetsTracked(unittest.TestCase):
    def test_pages_point_at_tracked_files(self):
        files = tracked()
        if not files:
            self.skipTest('not a git checkout')
        missing = []
        for page in sorted(DIST.rglob('*.html')):
            for raw in REFERENCE.findall(page.read_text(encoding='utf-8')):
                for ref in (part.split()[0] for part in raw.split(',') if part.strip()):
                    if re.match(r'[a-z][a-z0-9+.-]*:|//', ref):
                        continue
                    target = (DIST/ref.lstrip('/') if ref.startswith('/') else page.parent/ref).resolve()
                    if target.is_dir():
                        target = target/'index.html'
                    if DIST.resolve() in target.parents and target not in files:
                        missing.append(f'{page.relative_to(DIST)} -> {ref}')
        self.assertEqual([], missing)


if __name__ == '__main__':
    unittest.main()
