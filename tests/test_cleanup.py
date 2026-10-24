"""Acceptance tests for #25 task 1: cleanup of managed skill folders (black-box, via the sync CLI)."""
import os
import unittest

from tests.harness import SyncSandbox

MARKER = ".managed-by-devflow"


def _write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _read(path):
    with open(path) as f:
        return f.read()


class SkillCleanupTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def test_deselect_removes_marked_and_keeps_unmarked(self):
        # #23: skills folder in the table that is not an install folder has marker-carrying folders removed; user story 14
        sb = self.sb
        self.assertEqual(sb.run("providers", "claude,codex").returncode, 0)
        _write(sb.home_path("~/.agents/skills/mine/SKILL.md"), "mine\n")
        r = sb.run("providers", "claude")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), set())
        self.assertEqual(_read(sb.home_path("~/.agents/skills/mine/SKILL.md")), "mine\n")
        self.assertEqual(sb.managed_skills("~/.claude/skills"), sb.manifest_skill_names())
        self.assertIn("~/.agents/skills", [l.strip() for l in r.stdout.splitlines()])
        self.assertIn("removed tdd (provider not selected)", r.stdout)

    def test_cursor_with_claude_cleans_agents_folder(self):
        # #23: cursor rule: the shared folder is not an install folder when claude is also selected
        sb = self.sb
        sb.write_local(["cursor"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), sb.manifest_skill_names())
        sb.write_local(["claude", "cursor"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), set())
        self.assertEqual(sb.managed_skills("~/.claude/skills"), sb.manifest_skill_names())

    def test_prune_runs_on_every_install_folder(self):
        # characterization: passes today (#24 already prunes per install folder); #23 prune on every install folder
        sb = self.sb
        sb.write_local(["claude", "codex"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for d in ("~/.claude/skills", "~/.agents/skills"):
            _write(sb.home_path(d + "/old-skill/SKILL.md"), "old\n")
            _write(sb.home_path(d + "/old-skill/" + MARKER), "")
            _write(sb.home_path(d + "/mine-too/SKILL.md"), "mine\n")
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for d in ("~/.claude/skills", "~/.agents/skills"):
            self.assertFalse(os.path.exists(sb.home_path(d + "/old-skill")), d)
            self.assertTrue(os.path.isfile(sb.home_path(d + "/mine-too/SKILL.md")), d)
        self.assertEqual(r.stdout.count("removed old-skill (no longer in manifest)"), 2)

    def test_dry_run_deselect_writes_nothing(self):
        # #23: dry run reports and writes nothing
        sb = self.sb
        self.assertEqual(sb.run("providers", "claude,codex").returncode, 0)
        agents = sb.home_path("~/.agents/skills")
        listing = sorted(os.listdir(agents))
        with open(sb.local_file, "rb") as f:
            local_before = f.read()
        r = sb.run("providers", "claude", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(agents)), listing)
        with open(sb.local_file, "rb") as f:
            self.assertEqual(f.read(), local_before)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), sb.manifest_skill_names())
        self.assertIn("would remove tdd (provider not selected)", r.stdout)

    def test_symlinked_agents_folder_to_claude_is_not_cleaned(self):
        # Review Focus 1: cleanup folder resolving to an install folder is skipped and reported
        sb = self.sb
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        os.makedirs(sb.home_path("~/.agents"), exist_ok=True)
        os.symlink(sb.home_path("~/.claude/skills"), sb.home_path("~/.agents/skills"))
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.claude/skills"), sb.manifest_skill_names())
        self.assertIn("SKIP (same folder as an install folder)", r.stdout)

    def test_symlinked_skill_folder_is_never_followed(self):
        # Review Focus 2: a symlinked skill folder is never followed or deleted
        sb = self.sb
        ext = os.path.join(sb.home, "elsewhere", "ext")
        _write(os.path.join(ext, "SKILL.md"), "ext\n")
        _write(os.path.join(ext, MARKER), "")
        for d in ("~/.agents/skills", "~/.claude/skills"):
            os.makedirs(sb.home_path(d), exist_ok=True)
            os.symlink(ext, sb.home_path(d + "/ext"))
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for d in ("~/.agents/skills", "~/.claude/skills"):
            self.assertTrue(os.path.islink(sb.home_path(d + "/ext")), d)
        self.assertTrue(os.path.exists(os.path.join(ext, "SKILL.md")))

    def test_case_mismatched_symlink_to_claude_is_not_cleaned(self):
        sb = self.sb
        probe = os.path.join(sb.home, "CaseProbe")
        os.makedirs(probe)
        insensitive = os.path.exists(os.path.join(sb.home, "caseprobe"))
        os.rmdir(probe)
        if not insensitive:
            self.skipTest("case-sensitive filesystem")
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        os.makedirs(sb.home_path("~/.agents"), exist_ok=True)
        os.symlink(os.path.join(sb.home, ".CLAUDE", "skills"), sb.home_path("~/.agents/skills"))
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.claude/skills"), sb.manifest_skill_names())
        self.assertIn("SKIP (same folder as an install folder)", r.stdout)
        self.assertTrue(os.path.islink(sb.home_path("~/.agents/skills")))

    def test_default_output_unchanged_without_cleanup(self):
        # characterization: passes today; default selection prints no cleanup lines
        r = self.sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("provider not selected", r.stdout)
        self.assertNotIn("SKIP (same folder", r.stdout)


if __name__ == "__main__":
    unittest.main()
