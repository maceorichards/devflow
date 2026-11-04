"""A managed skill that can't be removed keeps its marker (#63 final review).

A failed removal must never leave a folder named after the skill that has lost
its `.managed-by-devflow` marker: a rerun of uninstall must still find it, and a
sync must still reinstall over it. Black-box through sync.sh in a SyncSandbox:
never run uninstall outside one.
"""
import os
import stat
import unittest

from tests.harness import SyncSandbox

MARKER = ".managed-by-devflow"
SKIP_UNMANAGED = "SKIP (exists, not managed by devflow)"


def _write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@unittest.skipIf(os.geteuid() == 0, "root ignores read-only folders")
class FailedRemovalKeepsMarkerTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)
        r = self.sb.run("providers", "claude")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.root = self.sb.home_path("~/.claude/skills")
        self.installed = self.sb.managed_skills("~/.claude/skills")
        self.assertIn("tdd", self.installed)

    def make_read_only(self, path):
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, path, stat.S_IRWXU)

    def fail_with_read_only_root(self):
        self.make_read_only(self.root)
        r = self.sb.run("uninstall")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertRegex(r.stdout, r"FAIL\s+tdd: could not remove: ")
        os.chmod(self.root, stat.S_IRWXU)
        return r

    def test_read_only_root_keeps_every_marker(self):
        self.fail_with_read_only_root()
        self.assertEqual(self.sb.managed_skills("~/.claude/skills"), self.installed)

    def test_rerun_after_read_only_root_removes_everything(self):
        self.fail_with_read_only_root()
        r = self.sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("removed tdd", r.stdout)
        self.assertEqual(self.sb.managed_skills("~/.claude/skills"), set())
        self.assertEqual(os.listdir(self.root), [])

    def test_sync_after_read_only_root_reinstalls(self):
        self.fail_with_read_only_root()
        r = self.sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(SKIP_UNMANAGED, r.stdout)
        self.assertEqual(self.sb.managed_skills("~/.claude/skills"), self.installed)

    def lock_inside_tdd(self):
        # a read-only subfolder with a file in it: the delete fails partway through tdd
        locked = os.path.join(self.root, "tdd", "locked")
        _write(os.path.join(locked, "f"), "x\n")
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
        # unlock whatever is left wherever it ended up
        self.addCleanup(self.unlock_leftovers)
        return locked

    def unlock_leftovers(self):
        os.chmod(self.root, stat.S_IRWXU)
        for dirpath, dirnames, _ in os.walk(self.root):
            for n in dirnames:
                os.chmod(os.path.join(dirpath, n), stat.S_IRWXU)

    def test_partial_delete_leaves_no_unmarked_skill_folder(self):
        self.lock_inside_tdd()
        r = self.sb.run("uninstall")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"FAIL\s+tdd: could not remove: ")
        tdd = os.path.join(self.root, "tdd")
        self.assertFalse(os.path.exists(tdd) and not os.path.exists(os.path.join(tdd, MARKER)))
        # tdd is back under its own name with its marker, so a rerun finds it
        self.assertIn("tdd", self.sb.managed_skills("~/.claude/skills"))
        self.assertEqual([n for n in os.listdir(self.root) if ".devflow-" in n], [])

    def test_partial_delete_then_rerun_and_sync(self):
        self.lock_inside_tdd()
        r = self.sb.run("uninstall")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.unlock_leftovers()
        r = self.sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.listdir(self.root), [])
        r = self.sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(SKIP_UNMANAGED, r.stdout)
        self.assertEqual(self.sb.managed_skills("~/.claude/skills"), self.installed)

    def test_partial_delete_then_sync_reinstalls(self):
        self.lock_inside_tdd()
        r = self.sb.run("uninstall")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.unlock_leftovers()
        r = self.sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(SKIP_UNMANAGED, r.stdout)
        self.assertEqual(self.sb.managed_skills("~/.claude/skills"), self.installed)
        self.assertEqual(sorted(os.listdir(self.root)), sorted(self.installed))


class RemovalSiblingNameTest(unittest.TestCase):
    def test_existing_sibling_folder_survives(self):
        sb = SyncSandbox()
        self.addCleanup(sb.close)
        r = sb.run("providers", "claude")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mine = sb.home_path("~/.claude/skills/tdd.devflow-gone/notes.txt")
        _write(mine, "mine\n")
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("removed tdd", r.stdout)
        self.assertEqual(sb.managed_skills("~/.claude/skills"), set())
        with open(mine, encoding="utf-8") as f:
            self.assertEqual(f.read(), "mine\n")
        self.assertEqual(os.listdir(sb.home_path("~/.claude/skills")), ["tdd.devflow-gone"])


if __name__ == "__main__":
    unittest.main()
