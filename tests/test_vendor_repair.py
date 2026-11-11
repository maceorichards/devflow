"""Regression test for the #52 final review: the one-time CRLF repair of a vendor clone must
survive a failed reset. If `git reset --hard` fails (on Windows, a file locked by antivirus or
an editor), the clone's local core.autocrlf must not yet read false, so the next sync retries
the repair. Black-box, through ./sync.sh in a SyncSandbox; the reset is made to fail by making
a folder of the clone read-only, so git can't replace the CRLF file inside it."""
import os
import stat
import unittest

from tests.harness import SyncSandbox, ignores_permissions
from tests.test_line_endings import _files_with_cr, _local_autocrlf


class FailedVendorRepairRetriesTest(unittest.TestCase):
    def setUp(self):
        if ignores_permissions():
            raise unittest.SkipTest("root and Windows ignore folder permissions, so the reset can't be made to fail")
        self.sb = SyncSandbox(own_vendors=True)
        self.addCleanup(self.sb.close)
        self.sb.set_global_git_config("core.autocrlf", "true")
        self.sb.clone_vendors()
        self.clone = self.sb.vendor_dirs()["matt"]
        crlf = _files_with_cr(self.sb, self.clone)
        self.assertNotEqual(crlf, [], "pre-cloned mattpocock-skills has no CRLF file under core.autocrlf=true")
        self.crlf_files = [os.path.join(self.clone, f) for f in crlf]
        self.locked = os.path.dirname(self.crlf_files[0])
        self.assertNotEqual(os.path.realpath(self.locked), os.path.realpath(self.clone))
        self.mode = stat.S_IMODE(os.stat(self.locked).st_mode)
        os.chmod(self.locked, 0o555)
        self.addCleanup(self.unlock)

    def unlock(self):
        os.chmod(self.locked, self.mode)

    def test_failed_reset_leaves_local_autocrlf_unset_to_false(self):
        r = self.sb.run()
        self.assertNotEqual(r.returncode, 0, "the reset was expected to fail:\n" + r.stdout + r.stderr)
        self.assertNotEqual(_local_autocrlf(self.sb, self.clone), "false", r.stdout + r.stderr)

    def test_next_sync_completes_the_repair(self):
        self.sb.run()
        self.unlock()
        r = self.sb.run()
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual(_local_autocrlf(self.sb, self.clone), "false", out)
        # Read the files directly: a clone left with an empty index lists no tracked files.
        still_crlf = []
        for p in self.crlf_files:
            with open(p, "rb") as f:
                if b"\r" in f.read():
                    still_crlf.append(os.path.relpath(p, self.clone))
        self.assertEqual(still_crlf, [], out)
        status = self.sb.git("status", "--porcelain", cwd=self.clone).stdout
        self.assertEqual(status, "", out)


if __name__ == "__main__":
    unittest.main()
