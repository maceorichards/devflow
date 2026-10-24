import os
import re
import unittest

from tests.harness import SyncSandbox

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


if __name__ == "__main__":
    unittest.main()
