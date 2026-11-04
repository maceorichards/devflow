"""Acceptance tests for #58, ticket #61: a new glossary's top heading is the GitHub repo name.

Black-box, via the sync CLI: build the skills in a SyncSandbox and read the installed
domain-modeling skill. The single-context line ships in the skill's GLOSSARY-FORMAT.md
(next to SKILL.md), so every installed .md file of the skill is searched for it. Every
assertion is scoped to the single-context paragraph (the one starting `**Single context`),
so a phrase elsewhere in the skill can't satisfy it.
"""
import os
import re
import unittest

from tests.harness import SyncSandbox

SKILL_DIR = "~/.claude/skills/domain-modeling"


def _single_context_paragraph(text):
    """The paragraph starting with `**Single context`, up to the next blank line."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("**Single context"):
            para = []
            for l in lines[i:]:
                if not l.strip():
                    break
                para.append(l)
            return "\n".join(para)
    return ""


class GlossaryHeadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = SyncSandbox()
        try:
            cls.result = cls.sb.run()
            d = cls.sb.home_path(SKILL_DIR)
            paras = []
            for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
                path = os.path.join(d, name)
                if name.endswith(".md") and os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        paras.append(_single_context_paragraph(f.read()))
            cls.para = "\n\n".join(p for p in paras if p)
        except Exception:
            cls.sb.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    def test_sync_succeeds_and_installs_the_single_context_line(self):
        # characterization: the sync and the line exist today; this guards the scoping
        r = self.result
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.para, "", "no **Single context line in the installed skill")

    def test_top_heading_is_the_github_repo_name(self):
        # #58, ticket #61: the top heading is the GitHub repo name
        self.assertRegex(
            self.para,
            re.compile(r"top heading.*GitHub repo(sitory)? name"
                       r"|GitHub repo(sitory)? name.*top heading", re.I | re.S))

    def test_gives_the_gh_command_that_reads_the_repo_name(self):
        # #58, ticket #61: read the name with `gh repo view --json name -q .name`
        self.assertRegex(
            self.para,
            re.compile(r"gh\s+repo\s+view\s+--json\s+name\s+-q\s+['\"]?\.name", re.I))

    def test_heading_rule_applies_when_creating_the_glossary(self):
        # #58, ticket #61: the rule applies when creating docs/GLOSSARY.md
        self.assertRegex(self.para, re.compile(r"creat", re.I))

    def test_existing_heading_is_never_renamed(self):
        # #58, ticket #61: never rename an existing heading
        self.assertRegex(
            self.para,
            re.compile(r"never\W+(\w+\W+){0,3}renam\w*\W+(\w+\W+){0,3}existing"
                       r"|existing\W+(\w+\W+){0,4}never\W+(\w+\W+){0,2}renam", re.I))


if __name__ == "__main__":
    unittest.main()
