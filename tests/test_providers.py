import json
import os
import re
import subprocess
import unittest

from tests.harness import REAL_ROOT, SyncSandbox

START = "<!-- devflow:start"
END = "<!-- devflow:end -->"


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class DefaultProviderTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def p(self, tilde):
        return self.sb.home_path(tilde)

    # characterization: no local file = behaviour as before (#23, user story 1)
    def test_no_local_file_installs_claude_only(self):
        sb = self.sb
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.claude/skills"), sb.manifest_skill_names())
        self.assertFalse(os.path.exists(self.p("~/.agents/skills")))
        md = read(self.p("~/.claude/CLAUDE.md"))
        self.assertIn(START, md)
        self.assertIn(END, md)
        self.assertFalse(os.path.exists(self.p("~/.codex/AGENTS.md")))
        self.assertFalse(os.path.exists(self.p("~/.gemini/GEMINI.md")))
        self.assertFalse(os.path.exists(sb.local_file))

    # characterization: second run changes nothing (#23, user story 1)
    def test_second_run_reports_unchanged(self):
        sb = self.sb
        self.assertEqual(sb.run().returncode, 0)
        first = read(self.p("~/.claude/CLAUDE.md"))
        r2 = sb.run()
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIsNone(re.search(r"^\s+(installed|updated)\s", r2.stdout, re.M), r2.stdout)
        second = read(self.p("~/.claude/CLAUDE.md"))
        self.assertEqual(first, second)
        self.assertEqual(second.count(START), 1)

    # characterization: unmanaged skill folders are never overwritten (#23, user story 1)
    def test_unmanaged_skill_folder_left_alone(self):
        sb = self.sb
        skill = self.p("~/.claude/skills/tdd/SKILL.md")
        write(skill, "mine\n")
        r = sb.run()
        self.assertEqual(read(skill), "mine\n")
        self.assertFalse(os.path.exists(self.p("~/.claude/skills/tdd/.managed-by-devflow")))
        self.assertIn("SKIP", r.stdout)

    # characterization: user text around the devflow section is preserved (#23, user story 1)
    def test_existing_claude_md_text_preserved(self):
        sb = self.sb
        md = self.p("~/.claude/CLAUDE.md")
        write(md, "# mine\nkeep me")
        sb.run()
        self.assertTrue(read(md).startswith("# mine\nkeep me\n\n" + START), read(md))
        write(md, "before\n" + START + " old -->\nold body\n" + END + "\nafter\n")
        sb.run()
        out = read(md)
        self.assertTrue(out.startswith("before\n" + START), out)
        self.assertTrue(out.endswith(END + "\nafter\n"), out)
        self.assertNotIn("old body", out)

    # characterization: git ignore lines added, existing kept (#23, user story 1)
    def test_git_ignore_lines_added_and_existing_kept(self):
        sb = self.sb
        ignore = self.p("~/.config/git/ignore")
        write(ignore, "*.swp\n")
        sb.run()
        lines = read(ignore).splitlines()
        self.assertIn("*.swp", lines)
        want = [l.strip() for l in read(os.path.join(sb.repo, "global", "git-ignore-lines")).splitlines()
                if l.strip() and not l.lstrip().startswith("#")]
        self.assertTrue(want)
        for line in want:
            self.assertIn(line, lines)


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def p(self, tilde):
        return self.sb.home_path(tilde)

    def stdout_lines(self, r):
        return [l.strip() for l in r.stdout.splitlines()]

    # #23, user stories 2, 3: codex alongside claude
    def test_claude_codex_installs_both(self):
        sb = self.sb
        sb.write_local(["claude", "codex"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        names = sb.manifest_skill_names()
        self.assertEqual(sb.managed_skills("~/.claude/skills"), names)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), names)
        self.assertIn(START, read(self.p("~/.claude/CLAUDE.md")))
        self.assertIn(START, read(self.p("~/.codex/AGENTS.md")))
        self.assertFalse(os.path.exists(self.p("~/.gemini/GEMINI.md")))

    # #23, user stories 4, 8: codex and gemini share one folder
    def test_codex_gemini_share_one_copy(self):
        sb = self.sb
        sb.write_local(["codex", "gemini"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), sb.manifest_skill_names())
        for entry in os.listdir(self.p("~/.agents/skills")):
            self.assertFalse(entry.endswith(".devflow-new") or entry.endswith(".devflow-old"), entry)
        self.assertIn(START, read(self.p("~/.codex/AGENTS.md")))
        self.assertIn(START, read(self.p("~/.gemini/GEMINI.md")))
        self.assertFalse(os.path.exists(self.p("~/.claude/skills")))
        self.assertFalse(os.path.exists(self.p("~/.claude/CLAUDE.md")))
        self.assertEqual(self.stdout_lines(r).count("~/.agents/skills"), 1, r.stdout)

    # #23, user stories 6, 7: cursor skips its own copy when claude covers it
    def test_claude_cursor_skips_agents_folder(self):
        sb = self.sb
        sb.write_local(["claude", "cursor"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.p("~/.agents/skills")))
        self.assertEqual(sb.managed_skills("~/.claude/skills"), sb.manifest_skill_names())
        self.assertIn("Customize \u2192 Rules", r.stdout)

    # #23, user stories 5, 6: cursor alone
    def test_cursor_alone_installs_agents_folder(self):
        sb = self.sb
        sb.write_local(["cursor"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), sb.manifest_skill_names())
        self.assertIn("Customize \u2192 Rules", r.stdout)
        self.assertFalse(os.path.exists(self.p("~/.claude/CLAUDE.md")))

    # #23, user story 7: codex does not install into a folder cursor reads
    def test_codex_cursor_installs_agents_folder(self):
        sb = self.sb
        sb.write_local(["codex", "cursor"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sb.managed_skills("~/.agents/skills"), sb.manifest_skill_names())

    # #23, user story 3: user text around the section survives
    def test_existing_agents_md_section_replaced_in_place(self):
        sb = self.sb
        agents = self.p("~/.codex/AGENTS.md")
        write(agents, "before\n<!-- devflow:start x -->\nstale\n<!-- devflow:end -->\nafter\n")
        sb.write_local(["codex"])
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = read(agents)
        self.assertTrue(out.startswith("before\n"), out)
        self.assertTrue(out.endswith("\nafter\n"), out)
        self.assertNotIn("stale", out)
        self.assertEqual(out.count(START), 1, out)

    # #23, user story 11: a bad local file never falls back, never writes
    def test_bad_local_file_rejected_and_nothing_written(self):
        cases = [
            ("unknown", ["claude", "cdx"], None),
            ("empty", [], None),
            ("malformed", None, "{not json"),
            ("non-list", None, "{\"providers\": \"claude\"}"),
        ]
        for label, providers, raw in cases:
            with self.subTest(label):
                with SyncSandbox() as sb:
                    if raw is None:
                        sb.write_local(providers)
                    else:
                        with open(sb.local_file, "w") as f:
                            f.write(raw)
                    r = sb.run()
                    self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertEqual(os.listdir(sb.home_path("~")), [], r.stdout + r.stderr)
                    if label == "unknown":
                        self.assertIn("unknown provider: cdx", r.stderr)

    # #23, user story 15: dry run reports per provider and writes nothing
    def test_dry_run_writes_nothing(self):
        sb = self.sb
        sb.write_local(["claude", "codex"])
        r = sb.run("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.listdir(sb.home_path("~")), [])
        self.assertIn("(dry run)", r.stdout)
        lines = self.stdout_lines(r)
        self.assertIn("~/.claude/skills", lines)
        self.assertIn("~/.agents/skills", lines)
        self.assertIn("would install", r.stdout)
        self.assertIn("would update ~/.codex/AGENTS.md devflow section", r.stdout)


class ProvidersCommandTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)

    def stdout_lines(self, r):
        return [l.strip() for l in r.stdout.splitlines()]

    def local(self):
        with open(self.sb.local_file) as f:
            return json.load(f)

    # #23, user story 5: choose providers with one command, then sync
    def test_providers_writes_local_file_and_syncs(self):
        sb = self.sb
        r = sb.run("providers", "claude,codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(sb.local_file), r.stdout + r.stderr)
        self.assertEqual(self.local(), {"providers": ["claude", "codex"]})
        names = sb.manifest_skill_names()
        self.assertEqual(sb.managed_skills("~/.agents/skills"), names)
        self.assertEqual(sb.managed_skills("~/.claude/skills"), names)
        r2 = sb.run()
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("~/.agents/skills", self.stdout_lines(r2))

    # #23, user story 5: spaces stripped, duplicates dropped, order kept
    def test_providers_dedupes_and_strips(self):
        sb = self.sb
        r = sb.run("providers", "claude, codex,codex")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(sb.local_file), r.stdout + r.stderr)
        self.assertEqual(self.local(), {"providers": ["claude", "codex"]})

    # #23, user story 5: unknown name rejected before anything is written
    def test_unknown_provider_writes_nothing(self):
        sb = self.sb
        sb.write_local(["claude"])
        with open(sb.local_file, "rb") as f:
            before = f.read()
        r = sb.run("providers", "claude,cdx")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("unknown provider: cdx", r.stderr)
        with open(sb.local_file, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(os.listdir(sb.home_path("~")), [])

    # #23, user story 5: an empty selection is rejected
    def test_empty_providers_rejected(self):
        for raw in ("", ","):
            with self.subTest(raw=raw):
                with SyncSandbox() as sb:
                    r = sb.run("providers", raw)
                    self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertFalse(os.path.exists(sb.local_file))
                    self.assertEqual(os.listdir(sb.home_path("~")), [])

    # #23, user story 15: dry run previews the choice and writes nothing
    def test_providers_dry_run_writes_nothing(self):
        sb = self.sb
        r = sb.run("providers", "codex,gemini", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(sb.local_file))
        self.assertEqual(os.listdir(sb.home_path("~")), [])
        self.assertIn("~/.agents/skills", r.stdout)
        self.assertIn("would update ~/.codex/AGENTS.md devflow section", r.stdout)
        self.assertIn("would update ~/.gemini/GEMINI.md devflow section", r.stdout)

    # #23, user story 5: the per-machine choice is not committed
    def test_local_file_is_git_ignored(self):
        r = subprocess.run(["git", "check-ignore", "-q", "devflow.local.json"],
                           cwd=REAL_ROOT)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
