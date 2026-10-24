import os
import unittest

from tests.harness import SyncSandbox

SKILLS = "~/.claude/skills"
FORBIDDEN = ("~/.claude/skills/", ".claude/docs/", "CLAUDE.local.md")
# #23, "Sibling paths": referencing skill -> relative path it must use
SIBLINGS = {
    "dev-multi": "../run-lanes/lane-heuristics.md",
    "to-tickets": "../run-lanes/lane-heuristics.md",
    "implement-spec": "../tdd/tester-brief.md",
    "subagent-driven-development": "../tdd/tester-brief.md",
}


def read(path):
    with open(path) as f:
        return f.read()


def text_files(root):
    for dirpath, _, names in os.walk(root):
        for n in names:
            p = os.path.join(dirpath, n)
            try:
                yield p, read(p)
            except (UnicodeDecodeError, OSError):
                continue


class NeutralPathsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = SyncSandbox()
        r = cls.sb.run()
        cls.sync_result = r

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    def setUp(self):
        r = self.sync_result
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def skill_dir(self, name):
        return os.path.join(self.sb.home_path(SKILLS), name)

    # #23, user story 16/17/25: no built skill bakes in Claude-specific paths
    def test_no_built_skill_mentions_claude_specific_paths(self):
        for bad in FORBIDDEN:
            with self.subTest(forbidden=bad):
                offenders = []
                for name in sorted(self.sb.manifest_skill_names()):
                    for path, text in text_files(self.skill_dir(name)):
                        if bad in text:
                            offenders.append("%s: %s" % (name, os.path.relpath(path, self.skill_dir(name))))
                self.assertEqual(offenders, [], "%r found in installed skills" % bad)

    # #23, user story 22/23: add .devflow/, never delete existing lines
    def test_git_ignore_gains_devflow_and_keeps_existing_lines(self):
        with SyncSandbox() as sb:
            ignore = os.path.join(sb.home, ".config", "git", "ignore")
            os.makedirs(os.path.dirname(ignore))
            with open(ignore, "w") as f:
                f.write("*.swp\n.claude/docs/\nCLAUDE.local.md\n")
            r = sb.run()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            lines = read(ignore).splitlines()
            for want in (".devflow/", "*.swp", ".claude/docs/", "CLAUDE.local.md"):
                with self.subTest(line=want):
                    self.assertIn(want, lines)

    # #23, user story 16/19: devflow section in CLAUDE.md uses .devflow/agents/
    def test_global_section_points_at_devflow_agents(self):
        md = read(self.sb.home_path("~/.claude/CLAUDE.md"))
        self.assertIn(".devflow/agents/", md)
        self.assertNotIn(".claude/docs/", md)

    # #23, user story 25: sibling-skill references are relative
    def test_sibling_paths_are_relative(self):
        for name, rel in SIBLINGS.items():
            with self.subTest(skill=name):
                text = read(os.path.join(self.skill_dir(name), "SKILL.md"))
                self.assertIn(rel, text)
