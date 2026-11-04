"""Acceptance tests for #58, ticket #59: the working-directory rule (black-box, via the sync CLI).

Workflows run from the main checkout and reach a worktree with `git -C` or a subshell
`(cd … && …)`, never a bare `cd` (#58, Implementation Decisions, "Working directory (#19)").
These pin that each rule's key phrases reach the installed text the agent reads.
"""
import re
import unittest

from tests.harness import SyncSandbox

START = "<!-- devflow:start"
END = "<!-- devflow:end -->"

# a subshell `(cd`, not a command substitution `$(cd`
SUBSHELL_CD = re.compile(r"(?<!\$)\(cd\b")
NEVER_BARE_CD = re.compile(r"never\b[^.\n]{0,20}?\bbare\s+`?cd\b", re.IGNORECASE)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _section(text, heading):
    """From `heading` up to the next `## ` heading (or the end of the file)."""
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start:] if nxt == -1 else text[start:nxt]


def _paragraphs(text):
    return re.split(r"\n\s*\n", text)


class InstalledWorkingDirectoryRuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = SyncSandbox()
        try:
            cls.result = cls.sb.run()
            md = _read(cls.sb.home_path("~/.claude/CLAUDE.md"))
            cls.devflow = md[md.index(START):md.index(END)]
            fin = _read(cls.sb.home_path("~/.claude/skills/finishing-a-development-branch/SKILL.md"))
            cls.finishing_step2 = _section(fin, "## Step 2")
            sdd = _read(cls.sb.home_path("~/.claude/skills/subagent-driven-development/SKILL.md"))
            done = [p for p in _paragraphs(sdd)
                    if p.lstrip().startswith("**DONE:**") and "review-package" in p]
            cls.sdd_done = done[0] if done else ""
        except Exception:
            cls.sb.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    def test_sync_succeeds(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)

    # devflow section (#58, ticket #59 criterion 1)

    def test_devflow_section_says_workflows_run_from_main_checkout(self):
        # "live in the main checkout's .devflow/" (agent docs) must not count
        self.assertRegex(
            self.devflow,
            re.compile(r"\b(runs?|work|works|stays?)\b[^.\n]{0,40}?\b(from|in)\s+the\s+main\s+checkout\b(?!')",
                       re.IGNORECASE))

    def test_devflow_section_names_git_dash_c(self):
        self.assertRegex(self.devflow, re.compile(r"`?git -C\b"))

    def test_devflow_section_names_cd_subshell(self):
        self.assertRegex(self.devflow, re.compile(r"(?<!\$)\(cd\b[^\n]*?&&"))

    def test_devflow_section_says_never_a_bare_cd(self):
        self.assertRegex(self.devflow, NEVER_BARE_CD)

    # finishing-a-development-branch, Step 2 environment detection (#58, ticket #59 criterion 2)

    def test_finishing_step2_tells_devflow_callers_to_use_a_subshell(self):
        hits = [p for p in _paragraphs(self.finishing_step2)
                if re.search(r"devflow", p, re.IGNORECASE) and SUBSHELL_CD.search(p)]
        self.assertTrue(hits, "no paragraph in Step 2 names devflow and a `(cd` subshell:\n"
                        + self.finishing_step2)

    # subagent-driven-development, DONE / review-package step (#58, ticket #59 criterion 3)

    def test_sdd_done_step_runs_review_package_in_a_subshell(self):
        self.assertRegex(self.sdd_done, SUBSHELL_CD)

    def test_sdd_done_step_says_never_a_bare_cd(self):
        self.assertRegex(self.sdd_done, NEVER_BARE_CD)


if __name__ == "__main__":
    unittest.main()
