"""#58 final-review fixes: worktree subshells that actually work, and when the mode line is stated.

Black-box: `sync.sh` runs in a SyncSandbox and the installed SKILL.md files are read from the
sandbox HOME. These pin each fix's key phrases (case-insensitive), not whole sentences.
"""
import re
import unittest

from tests.harness import SyncSandbox

SUBSHELL_CD = re.compile(r"(?<!\$)\(cd\b")


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


def _block(text, start):
    """From the line starting with `start` up to the next blank line or heading ('' if absent)."""
    m = re.search(r"^" + re.escape(start) + r".*?(?=\n\s*\n|\n#|\Z)", text, re.M | re.S)
    return m.group(0) if m else ""


def _units(text):
    """Sentences, also split at line ends (bullets)."""
    return [u for u in re.split(r"(?<=[.!?])\s+|\n", text) if u.strip()]


def _has_unit_with(text, *patterns):
    return any(all(re.search(p, u, re.I) for p in patterns) for u in _units(text))


def _lines_with(text, pattern):
    return [l for l in text.splitlines() if re.search(pattern, l, re.I)]


class InstalledReviewFixesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sb = SyncSandbox()
        try:
            r = sb.run()
            cls.sync_ok = (r.returncode == 0, r.stdout + r.stderr)
            skill = lambda name: _read(sb.home_path("~/.claude/skills/%s/SKILL.md" % name))
            fin = _section(skill("finishing-a-development-branch"), "## Step 2")
            cls.fin_devflow = "\n\n".join(p for p in _paragraphs(fin)
                                          if re.search("devflow", p, re.I) and SUBSHELL_CD.search(p))
            sdd = skill("subagent-driven-development")
            done = [p for p in _paragraphs(sdd)
                    if p.lstrip().startswith("**DONE:**") and "review-package" in p]
            cls.sdd_done = done[0] if done else ""
            cls.multi = skill("dev-multi")
            cls.single = skill("dev-single")
        finally:
            sb.close()

    def test_sync_succeeds(self):
        self.assertTrue(self.sync_ok[0], self.sync_ok[1])

    # Finding 1: finishing's devflow subshell covers Steps 1-2 and prints what later steps use.

    def test_finishing_subshell_covers_steps_1_and_2(self):
        self.assertRegex(self.fin_devflow, re.compile(r"Steps\s+1\s*[–-]\s*2"))

    def test_finishing_subshell_prints_worktree_path(self):
        self.assertRegex(self.fin_devflow, re.compile(r"\(cd\b[^\n]*?&&[^\n]*?echo\b[^\n]*?\$WORKTREE_PATH"))

    def test_finishing_subshell_uses_no_undefined_wt_variable(self):
        self.assertNotIn("$WT", self.fin_devflow)

    # Finding 2: SDD's DONE subshell calls review-package by its path in this skill's directory.

    def test_sdd_done_subshell_calls_review_package_by_skill_dir_path(self):
        self.assertRegex(
            self.sdd_done,
            re.compile(r"\(cd\b[^\n]*?&&\s*bash\s+<this skill's dir>/scripts/review-package"))

    def test_sdd_done_has_no_relative_script_path(self):
        self.assertNotIn("bash scripts/review-package", self.sdd_done)

    # Finding 3: on #N the mode line comes after the recorded mode is read; fallback stated.

    def test_dev_multi_mode_line_on_resume_waits_for_state_file(self):
        lines = _lines_with(self.multi, r"state the mode in one line")
        self.assertTrue(any(re.search(r"#N", l) and re.search(r"state file", l, re.I) for l in lines),
                        lines)

    def test_dev_single_mode_line_on_resume_waits_for_state_file(self):
        lines = _lines_with(self.single, r"state the mode in one line")
        self.assertTrue(any(re.search(r"#N", l) and re.search(r"state file", l, re.I) for l in lines),
                        lines)

    def test_dev_multi_flagless_resume_without_recorded_mode_is_mixed(self):
        self.assertTrue(_has_unit_with(self.multi, r"recorded mode", r"MIXED if none"))

    def test_dev_multi_mode_bullet_agrees_upgrade_is_mixed(self):
        self.assertTrue(_has_unit_with(self.multi, r"^\s*- Neither", r"\bMIXED\b", r"upgrade"))

    def test_dev_single_flagless_resume_without_recorded_mode_is_fast(self):
        self.assertTrue(_has_unit_with(_block(self.single, "**Resuming"),
                                       r"recorded mode", r"FAST if none"))

    # Finding 4: dev-single can't build MIXED, so a recorded MIXED resumes as FAST.

    def test_dev_single_recorded_mixed_resumes_as_fast(self):
        self.assertTrue(_has_unit_with(_block(self.single, "**Resuming"),
                                       r"\bFAST if\b[^.;]*\bMIXED\b"))


if __name__ == "__main__":
    unittest.main()
