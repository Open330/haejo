"""Finished runs from earlier days are merged one file per day, and still read back per run."""
import json, os, tempfile, time, unittest
from pathlib import Path
from haejo import access_log as al


def write_run(root, name, rows, mtime):
    path = root/name
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    os.utime(path, (mtime, mtime))
    return path


class DayLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.now = time.mktime((2026, 11, 11, 12, 0, 0, 0, 0, -1))

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, inv):
        return [{'schema': 1, 'sequence': 1, 'event': 'command_start', 'command': 'observe', 'invocation_id': inv},
                {'schema': 1, 'sequence': 2, 'event': 'command_end', 'exit_code': 0}]

    def test_old_idle_runs_merge_into_their_day_and_read_back(self):
        old = 'haejo-20261110T010203040506Z-' + 'a' * 32 + '.jsonl'
        write_run(self.root, old, self.rows('1' * 32), self.now - 86400)
        today = 'haejo-20261111T010203040506Z-' + 'b' * 32 + '.jsonl'
        write_run(self.root, today, self.rows('2' * 32), self.now - 7200)
        self.assertEqual(2, al.compact(self.root, now=self.now))
        self.assertFalse((self.root/old).exists())
        self.assertFalse((self.root/today).exists(), 'a finished run of today merges too')
        self.assertTrue((self.root/'haejo-day-20261111.jsonl').exists())
        day = (self.root/'haejo-day-20261110.jsonl').read_text().splitlines()
        self.assertTrue(all(json.loads(l)['run'] == old for l in day))
        back = [json.loads(l) for l in al.read_run(old, root=self.root).decode().splitlines()]
        self.assertEqual(self.rows('1' * 32), back)
        self.assertEqual(self.rows('2' * 32), [json.loads(l) for l in al.read_run(today, root=self.root).decode().splitlines()])

    def test_a_run_still_being_written_is_not_moved(self):
        busy = 'haejo-20261110T235959000000Z-' + 'c' * 32 + '.jsonl'
        write_run(self.root, busy, self.rows('3' * 32), self.now - 60)
        self.assertEqual(0, al.compact(self.root, now=self.now))
        self.assertTrue((self.root/busy).exists())

    def test_a_crash_after_append_leaves_a_duplicate_not_a_loss(self):
        old = 'haejo-20261109T010203040506Z-' + 'd' * 32 + '.jsonl'
        write_run(self.root, old, self.rows('4' * 32), self.now - 2 * 86400)
        al.compact(self.root, now=self.now)
        # Simulate the file reappearing (crash before unlink) and merging again.
        write_run(self.root, old, self.rows('4' * 32), self.now - 2 * 86400)
        os.remove(self.root/old)
        day = self.root/'haejo-day-20261109.jsonl'
        day.write_text(day.read_text() * 2)
        self.assertEqual(2, len(al.read_run(old, root=self.root).decode().splitlines()))

    def test_only_one_process_merges_at_a_time(self):
        import fcntl
        old = 'haejo-20261110T010203040506Z-' + 'e' * 32 + '.jsonl'
        write_run(self.root, old, self.rows('5' * 32), self.now - 86400)
        fd = os.open(self.root/'.compact.lock', os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.assertEqual(0, al.compact(self.root, now=self.now))
        finally:
            os.close(fd)
        self.assertEqual(1, al.compact(self.root, now=self.now))

    def test_housekeeping_waits_its_interval_but_not_past_the_file_cap(self):
        write_run(self.root, 'haejo-20261111T010203040506Z-' + '9' * 32 + '.jsonl', self.rows('9' * 32), self.now)
        self.assertTrue(al.housekeeping(self.root, 30, now=self.now))
        self.assertFalse(al.housekeeping(self.root, 30, now=self.now + 60), 'skipped within the interval')
        self.assertTrue(al.housekeeping(self.root, 7, now=self.now + 60), 'a changed retention runs at once')
        from unittest import mock
        with mock.patch.object(al, 'MAX_FILES', 1):
            self.assertTrue(al.housekeeping(self.root, 7, now=self.now + 120), 'the cap is checked every time')

    def test_limit_is_disk_usage_and_raised(self):
        self.assertEqual(100 * 1024 * 1024, al.MAX_TOTAL)
        path = write_run(self.root, 'haejo-20261111T010203040506Z-' + 'f' * 32 + '.jsonl', self.rows('6' * 32), self.now)
        info = path.lstat()
        self.assertGreaterEqual(al._disk(info), info.st_size)


if __name__ == '__main__':
    unittest.main()
