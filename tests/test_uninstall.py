"""Acceptance tests for `./sync.sh uninstall` skills clearing (#63 user story k, ticket #64).

Black-box through sync.sh in a SyncSandbox: never run uninstall outside one.
"""
import os
import re
import stat
import unittest

from tests.harness import SyncSandbox, ignores_permissions, requires_posix_permissions, requires_symlinks

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
        if ignores_permissions():
            self.skipTest("needs read-only folders (POSIX, not root)")
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

    @requires_symlinks
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

    @requires_symlinks
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

    @requires_symlinks
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

    @requires_symlinks
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

    @requires_posix_permissions
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


def _section(text):
    """The devflow section (start marker through end marker) of an instructions file."""
    start = text.index("<!-- devflow:start")
    end = text.index("<!-- devflow:end -->") + len("<!-- devflow:end -->")
    return text[start:end]


class UninstallInstructionsTest(unittest.TestCase):
    """Instructions files, notes and closing lines (#63 user story k, ticket #64)."""

    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def install(self, providers="claude,codex"):
        r = self.sb.run("providers", providers)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def uninstall(self, *args):
        r = self.sb.run("uninstall", *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_sections_removed_from_every_instructions_file(self):
        sb = self.sb
        self.install()
        r = self.uninstall()
        self.assertNotIn("<!-- devflow:start", _read(sb.home_path("~/.claude/CLAUDE.md")))
        self.assertNotIn("<!-- devflow:start", _read(sb.home_path("~/.codex/AGENTS.md")))
        self.assertIn("removed ~/.claude/CLAUDE.md devflow section", r.stdout)
        self.assertIn("removed ~/.codex/AGENTS.md devflow section", r.stdout)

    def test_section_removed_for_unselected_provider(self):
        sb = self.sb
        self.install("claude")
        section = _section(_read(sb.home_path("~/.claude/CLAUDE.md")))
        gemini = sb.home_path("~/.gemini/GEMINI.md")
        _write(gemini, "gemini notes\n\n" + section + "\n")
        self.uninstall()
        self.assertNotIn("<!-- devflow:start", _read(gemini))

    def test_user_text_around_markers_kept(self):
        sb = self.sb
        self.install()
        path = sb.home_path("~/.claude/CLAUDE.md")
        _write(path, "before\n\n" + _section(_read(path)) + "\n\nafter\n")
        self.uninstall()
        text = _read(path)
        self.assertIn("before", text)
        self.assertIn("after", text)
        self.assertNotIn("devflow:start", text)

    def test_incomplete_markers_left_untouched_and_counted(self):
        sb = self.sb
        self.install()
        path = sb.home_path("~/.codex/AGENTS.md")
        content = "mine\n<!-- devflow:start -->\nhalf\n"
        _write(path, content)
        r = self.uninstall()
        self.assertEqual(_read(path), content)
        self.assertIn("SKIP ~/.codex/AGENTS.md: devflow markers incomplete, left untouched",
                      r.stdout)
        self.assertIn("1 item(s) left for you to remove by hand (see the SKIP lines above)",
                      r.stdout)

    @requires_symlinks
    def test_shared_instructions_file_handled_once(self):
        sb = self.sb
        self.install("claude")
        codex = sb.home_path("~/.codex/AGENTS.md")
        os.makedirs(os.path.dirname(codex), exist_ok=True)
        if os.path.lexists(codex):
            os.remove(codex)
        os.symlink(sb.home_path("~/.claude/CLAUDE.md"), codex)
        r = self.uninstall()
        self.assertIn("SKIP ~/.codex/AGENTS.md: same file as ~/.claude/CLAUDE.md, left untouched",
                      r.stdout)
        self.assertNotIn("item(s) left", r.stdout)

    @requires_symlinks
    def test_symlinked_instructions_file_stays_a_link(self):
        sb = self.sb
        self.install("claude")
        link = sb.home_path("~/.claude/CLAUDE.md")
        target = os.path.join(sb.tmp, "dotfiles", "CLAUDE.md")
        os.makedirs(os.path.dirname(target))
        os.rename(link, target)
        os.symlink(target, link)
        self.uninstall()
        self.assertTrue(os.path.islink(link))
        self.assertNotIn("devflow:start", _read(target))

    def test_section_only_file_kept_without_markers(self):
        sb = self.sb
        self.install("claude")
        path = sb.home_path("~/.claude/CLAUDE.md")
        self.assertIn("devflow:start", _read(path))
        self.uninstall()
        self.assertTrue(os.path.isfile(path))
        self.assertNotIn("devflow:start", _read(path))

    def test_notes_block(self):
        sb = self.sb
        self.install()
        ignore = sb.home_path("~/.config/git/ignore")
        before = _read(ignore) if os.path.exists(ignore) else None
        r = self.uninstall()
        lines = r.stdout.splitlines()
        self.assertIn("notes", lines)
        i = lines.index("notes")
        self.assertEqual(lines[i + 1:i + 5], [
            "  git ignore lines kept in ~/.config/git/ignore: .devflow/, .worktrees/, .claude/worktrees/",
            "  Cursor: delete the devflow section from Customize \u2192 Rules if you added it",
            "  kept: this clone (devflow.local.json, vendor/) and every project's .devflow/ and .worktrees/",
            "  to reinstall: ./sync.sh",
        ])
        after = _read(ignore) if os.path.exists(ignore) else None
        self.assertEqual(after, before)

    def test_blocks_in_order(self):
        self.install()
        lines = self.uninstall().stdout.splitlines()
        blocks = ("~/.claude/skills", "instructions", "notes")
        for b in blocks:
            self.assertIn(b, lines)
        idx = [lines.index(b) for b in blocks]
        self.assertEqual(idx, sorted(idx))
        self.assertEqual(len(set(idx)), 3)

    def test_second_run_nothing_to_remove(self):
        sb = self.sb
        self.install()
        self.uninstall()
        before = snapshot(sb.home)
        r = self.uninstall()
        lines = r.stdout.splitlines()
        self.assertIn("nothing to remove", lines)
        self.assertEqual([l for l in lines if l.startswith("  removed")], [])
        self.assertEqual(snapshot(sb.home), before)

    def test_fresh_home_nothing_to_remove_creates_nothing(self):
        sb = self.sb
        before = snapshot(sb.home)
        r = self.uninstall()
        self.assertIn("nothing to remove", r.stdout.splitlines())
        self.assertEqual(snapshot(sb.home), before)

    def test_local_file_kept(self):
        # characterization: uninstall never touches devflow.local.json (may already pass)
        sb = self.sb
        sb.write_local(["claude", "codex"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        path = os.path.join(sb.repo, "devflow.local.json")
        before = _read(path)
        self.uninstall()
        self.assertEqual(_read(path), before)


if __name__ == "__main__":
    unittest.main()
