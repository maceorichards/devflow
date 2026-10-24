"""Acceptance tests for #31: follow-ups from #23 (black-box, via the sync CLI)."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

from tests import harness
from tests.harness import SyncSandbox

START = "<!-- devflow:start"
MARKER = ".managed-by-devflow"


def _write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _read(path):
    with open(path) as f:
        return f.read()


class RemoveFailureTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def lock(self, skill_dir):
        # a read-only subfolder with a file in it: rmtree cannot unlink the file
        locked = os.path.join(skill_dir, "locked")
        _write(os.path.join(locked, "f"), "x\n")
        os.chmod(locked, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, locked, stat.S_IRWXU)

    def test_prune_failure_reported_and_run_continues(self):
        sb = self.sb
        old = sb.home_path("~/.claude/skills/old-skill")
        _write(os.path.join(old, "SKILL.md"), "old\n")
        _write(os.path.join(old, MARKER), "")
        self.lock(old)
        r = sb.run()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertRegex(r.stdout, r"FAIL\s+old-skill: ")
        self.assertIn(START, _read(sb.home_path("~/.claude/CLAUDE.md")))
        self.assertTrue(os.path.exists(sb.home_path("~/.config/git/ignore")), r.stdout)

    def test_cleanup_failure_reported_and_run_continues(self):
        sb = self.sb
        self.assertEqual(sb.run("providers", "claude,codex").returncode, 0)
        self.lock(sb.home_path("~/.agents/skills/tdd"))
        r = sb.run("providers", "claude")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertRegex(r.stdout, r"FAIL\s+tdd: ")
        self.assertIn("removed grill-me (provider not selected)", r.stdout)
        self.assertNotIn(START, _read(sb.home_path("~/.codex/AGENTS.md")))
        self.assertIn("removed ~/.codex/AGENTS.md devflow section", r.stdout)


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def test_instructions_file_replaced_not_rewritten(self):
        sb = self.sb
        md = sb.home_path("~/.claude/CLAUDE.md")
        _write(md, "# mine\n")
        os.chmod(md, 0o640)
        ino = os.stat(md).st_ino
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(os.stat(md).st_ino, ino)
        self.assertEqual(stat.S_IMODE(os.stat(md).st_mode), 0o640)
        self.assertEqual(sorted(os.listdir(sb.home_path("~/.claude"))), ["CLAUDE.md", "skills"])

    def test_removed_section_file_replaced_not_rewritten(self):
        sb = self.sb
        self.assertEqual(sb.run("providers", "claude,codex").returncode, 0)
        agents = sb.home_path("~/.codex/AGENTS.md")
        ino = os.stat(agents).st_ino
        r = sb.run("providers", "claude")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(os.stat(agents).st_ino, ino)
        self.assertEqual(os.listdir(sb.home_path("~/.codex")), ["AGENTS.md"])

    def test_symlinked_instructions_file_stays_a_link(self):
        sb = self.sb
        target = os.path.join(sb.home, "dotfiles", "CLAUDE.md")
        _write(target, "# mine\n")
        os.makedirs(sb.home_path("~/.claude"))
        os.symlink(target, sb.home_path("~/.claude/CLAUDE.md"))
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.islink(sb.home_path("~/.claude/CLAUDE.md")))
        self.assertIn(START, _read(target))
        self.assertEqual(os.listdir(os.path.dirname(target)), ["CLAUDE.md"])

    def test_local_file_replaced_not_rewritten(self):
        sb = self.sb
        sb.write_local(["claude"])
        ino = os.stat(sb.local_file).st_ino
        r = sb.run("providers", "claude,codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(os.stat(sb.local_file).st_ino, ino)
        with open(sb.local_file) as f:
            self.assertEqual(json.load(f), {"providers": ["claude", "codex"]})
        self.assertEqual([n for n in os.listdir(sb.repo) if n.startswith("devflow.local")],
                         ["devflow.local.json"])


class LocalFileTest(unittest.TestCase):
    def test_unreadable_local_file_rejected_without_traceback(self):
        with SyncSandbox() as sb:
            os.makedirs(sb.local_file)
            r = sb.run()
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('expected {"providers": [...]}', r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertEqual(os.listdir(sb.home_path("~")), [])


class ReminderTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def test_reminder_follows_rows_without_instructions(self):
        sb = self.sb
        path = os.path.join(sb.repo, "manifest.json")
        with open(path) as f:
            man = json.load(f)
        man["providers"].append({"name": "zed", "skills_dir": "~/.agents/skills",
                                 "instructions": None, "also_reads": []})
        with open(path, "w") as f:
            json.dump(man, f, indent=2)
        r = sb.run("providers", "zed", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("note: zed ", r.stdout)
        self.assertNotIn("note: cursor", r.stdout)
        r = sb.run("providers", "claude,codex", "--dry-run")
        self.assertNotIn("note:", r.stdout)


class OutputOrderTest(unittest.TestCase):
    def test_blocks_in_order_note_last(self):
        with SyncSandbox() as sb:
            self.assertEqual(sb.run("providers", "claude,codex").returncode, 0)
            r = sb.run("providers", "claude,cursor")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            lines = [l.strip() for l in r.stdout.splitlines()]
            install = lines.index("~/.claude/skills")
            cleanup = lines.index("~/.agents/skills")
            instructions = lines.index("instructions")
            ignore = [i for i, l in enumerate(lines) if "git ignore" in l or "~/.config/git/ignore" in l]
            self.assertEqual(len(ignore), 1, r.stdout)
            self.assertLess(install, cleanup)
            self.assertLess(cleanup, instructions)
            self.assertLess(instructions, ignore[0])
            self.assertEqual(ignore[0], len(lines) - 2, r.stdout)
            self.assertTrue(lines[-1].startswith("note: cursor "), r.stdout)
            self.assertEqual(lines.count("devflow sync"), 1, r.stdout)


class ProvidersArgsTest(unittest.TestCase):
    def test_bad_argument_shapes_print_usage_and_write_nothing(self):
        for args in (("providers", "claude", "codex"),
                     ("providers", "--dry-run", "claude"),
                     ("providers",),
                     ("providers", "claude", "--dry-run", "x")):
            with self.subTest(args=args):
                with SyncSandbox() as sb:
                    r = sb.run(*args)
                    self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertIn("Usage", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertFalse(os.path.exists(sb.local_file))
                    self.assertEqual(os.listdir(sb.home_path("~")), [])

    def test_dry_run_header_printed_once(self):
        with SyncSandbox() as sb:
            r = sb.run("providers", "claude", "--dry-run")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(r.stdout.count("devflow sync (dry run)"), 1, r.stdout)


class ThreeProviderTest(unittest.TestCase):
    def test_claude_codex_cursor_installs_both_folders(self):
        with SyncSandbox() as sb:
            r = sb.run("providers", "claude,codex,cursor")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            names = sb.manifest_skill_names()
            self.assertEqual(sb.managed_skills("~/.claude/skills"), names)
            self.assertEqual(sb.managed_skills("~/.agents/skills"), names)
            self.assertIn(START, _read(sb.home_path("~/.codex/AGENTS.md")))
            self.assertIn("Customize → Rules", r.stdout)


class TrailingBlankLinesTest(unittest.TestCase):
    def test_section_at_end_with_extra_blank_lines_leaves_no_separator(self):
        with SyncSandbox() as sb:
            self.assertEqual(sb.run("providers", "claude,codex").returncode, 0)
            path = sb.home_path("~/.codex/AGENTS.md")
            cur = _read(path)
            a = cur.index(START)
            _write(path, "# mine\n\n" + cur[a:].rstrip("\n") + "\n\n\n")
            r = sb.run("providers", "claude")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(_read(path), "# mine\n")


class VendorDriftTest(unittest.TestCase):
    def git(self, *args, cwd):
        subprocess.run(["git"] + list(args), cwd=cwd, check=True, capture_output=True)

    def fake_root(self, lock_sha):
        root = tempfile.mkdtemp(prefix="devflow-drift-")
        self.addCleanup(shutil.rmtree, root, True)
        clone = os.path.join(root, "vendor", "v")
        os.makedirs(clone)
        self.git("init", "-q", cwd=clone)
        _write(os.path.join(clone, "x"), "x\n")
        self.git("add", "x", cwd=clone)
        self.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x", cwd=clone)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=clone, capture_output=True,
                              text=True, check=True).stdout.strip()
        with open(os.path.join(root, "manifest.json"), "w") as f:
            json.dump({"vendors": {"v": {"url": "unused", "dir": "vendor/v"}}}, f)
        with open(os.path.join(root, "vendor.lock"), "w") as f:
            json.dump({"v": lock_sha or head}, f)
        return root, clone, head

    def test_drifted_clone_skips_with_message(self):
        root, clone, head = self.fake_root("0" * 40)
        with self.assertRaises(unittest.SkipTest) as cm:
            harness.check_vendors(root)
        self.assertIn("vendor/v", str(cm.exception))
        self.assertIn("vendor.lock", str(cm.exception))
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=clone, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), head)

    def test_matching_clone_passes(self):
        root, _, _ = self.fake_root(None)
        harness.check_vendors(root)

    def test_missing_clone_skips(self):
        root, clone, _ = self.fake_root(None)
        shutil.rmtree(clone)
        with self.assertRaises(unittest.SkipTest):
            harness.check_vendors(root)


if __name__ == "__main__":
    unittest.main()
