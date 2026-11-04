"""Acceptance tests for `./sync.sh uninstall` skills clearing (#63 user story k, ticket #64).

Black-box through sync.sh in a SyncSandbox: never run uninstall outside one.
"""
import os
import re
import stat
import unittest

from tests.harness import SyncSandbox

MARKER = ".managed-by-devflow"


def _write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def snapshot(root):
    """Every path under root (files, folders, links) -> (kind, content or link target)."""
    snap = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                snap[p] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                snap[p] = ("dir", None)
            else:
                snap[p] = ("file", _read(p) if stat.S_ISREG(st.st_mode) else None)
    return snap


class UninstallSkillsTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def install(self, providers="claude,codex"):
        r = self.sb.run("providers", providers)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def lock(self, skill_dir):
        # a read-only subfolder with a file in it: rmtree cannot unlink the file
        locked = os.path.join(skill_dir, "locked")
        _write(os.path.join(locked, "f"), "x\n")
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, locked, stat.S_IRWXU)

    def test_uninstall_removes_every_managed_skill(self):
        sb = self.sb
        self.install()
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.claude/skills"), set())
        self.assertEqual(sb.managed_skills("~/.agents/skills"), set())
        self.assertIn("removed tdd", r.stdout)
        self.assertEqual(r.stdout.splitlines()[0], "devflow uninstall")

    def test_removes_skills_of_unselected_providers(self):
        sb = self.sb
        self.install("claude")
        d = sb.home_path("~/.agents/skills/tdd")
        _write(os.path.join(d, "SKILL.md"), "x\n")
        _write(os.path.join(d, MARKER), "")
        sb.write_local(["claude"])
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), set())

    def test_marked_skill_not_in_manifest_removed(self):
        sb = self.sb
        self.install()
        d = sb.home_path("~/.claude/skills/old-skill")
        _write(os.path.join(d, "SKILL.md"), "old\n")
        _write(os.path.join(d, MARKER), "")
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(d))
        self.assertIn("removed old-skill", r.stdout)

    def test_crash_leftovers_removed(self):
        sb = self.sb
        self.install()
        d = sb.home_path("~/.claude/skills/tdd.devflow-new")
        _write(os.path.join(d, "SKILL.md"), "x\n")
        _write(os.path.join(d, MARKER), "")
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(d))

    def test_unmanaged_folder_survives(self):
        sb = self.sb
        self.install()
        f = sb.home_path("~/.claude/skills/mine/SKILL.md")
        _write(f, "mine\n")
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(_read(f), "mine\n")

    def test_symlinked_skill_folder_survives(self):
        sb = self.sb
        self.install()
        target = os.path.join(sb.tmp, "elsewhere", "linked")
        _write(os.path.join(target, "SKILL.md"), "x\n")
        _write(os.path.join(target, MARKER), "")
        link = sb.home_path("~/.claude/skills/linked")
        os.symlink(target, link)
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.isfile(os.path.join(target, "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(target, MARKER)))

    def test_link_inside_managed_skill_not_followed(self):
        sb = self.sb
        self.install()
        data = os.path.join(sb.tmp, "precious", "data.txt")
        _write(data, "keep\n")
        skill = sb.home_path("~/.claude/skills/tdd")
        os.symlink(os.path.join(sb.tmp, "precious"), os.path.join(skill, "precious"))
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(skill))
        self.assertEqual(_read(data), "keep\n")

    def test_symlinked_skills_root_cleared_link_kept(self):
        sb = self.sb
        real = os.path.join(sb.tmp, "dotfiles", "skills")
        os.makedirs(real)
        os.makedirs(sb.home_path("~/.claude"))
        os.symlink(real, sb.home_path("~/.claude/skills"))
        self.install("claude")
        self.assertNotEqual(sb.managed_skills("~/.claude/skills"), set())
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.islink(sb.home_path("~/.claude/skills")))
        self.assertEqual(sb.managed_skills("~/.claude/skills"), set())

    def test_shared_folder_processed_once(self):
        sb = self.sb
        os.makedirs(sb.home_path("~/.claude/skills"))
        os.makedirs(sb.home_path("~/.agents"))
        os.symlink(sb.home_path("~/.claude/skills"), sb.home_path("~/.agents/skills"))
        self.install("claude")
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("SKIP (same folder as ~/.claude/skills)"), 1, r.stdout)
        self.assertEqual(len(re.findall(r"^\s*removed tdd$", r.stdout, re.M)), 1, r.stdout)

    def test_dry_run_writes_nothing(self):
        sb = self.sb
        self.install()
        before = snapshot(sb.home)
        r = sb.run("uninstall", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(snapshot(sb.home), before)
        self.assertEqual(r.stdout.splitlines()[0], "devflow uninstall (dry run)")
        self.assertIn("would remove tdd", r.stdout)

    def test_works_without_vendor(self):
        sb = self.sb
        self.install()
        os.remove(os.path.join(sb.repo, "vendor"))
        r = sb.run("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.claude/skills"), set())
        self.assertEqual(sb.managed_skills("~/.agents/skills"), set())
        self.assertFalse(os.path.exists(os.path.join(sb.repo, "vendor")))
        self.assertNotIn("cloning", r.stdout)

    @unittest.skipIf(os.geteuid() == 0, "root ignores read-only folders")
    def test_failed_removal_reported_exit_1(self):
        sb = self.sb
        self.install()
        self.lock(sb.home_path("~/.claude/skills/tdd"))
        r = sb.run("uninstall")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertRegex(r.stdout, r"FAIL\s+tdd: could not remove: ")
        self.assertIn("1 folder(s) could not be removed", r.stdout)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), set())

    def test_extra_argument_prints_usage(self):
        sb = self.sb
        self.install()
        for args in (("uninstall", "claude"), ("uninstall", "--dry-run", "x"),
                     ("uninstall", "--force")):
            with self.subTest(args=args):
                r = sb.run(*args)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("sync.sh uninstall [--dry-run]", r.stdout + r.stderr)
                self.assertEqual(sb.managed_skills("~/.claude/skills"),
                                 sb.manifest_skill_names())


if __name__ == "__main__":
    unittest.main()
