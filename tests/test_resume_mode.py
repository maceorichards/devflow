"""Acceptance tests for #58, ticket #60: a resume keeps the recorded mode, and `#N` parsing.

Black-box: `sync.sh` runs in a SyncSandbox and the installed dev-multi and dev-single
SKILL.md files are read from the sandbox HOME. The smoke checklist is read from the repo.
These pin each rule's key phrases (case-insensitive), not whole sentences.
"""
import os
import re
import unittest

from tests.harness import SyncSandbox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Phrases saying "no --fast / --rigor flag was given".
FLAGLESS = r"flagless|\bno\s+(?:mode\s+)?flags?\b|without\s+(?:a\s+)?(?:mode\s+)?flags?\b"
ISSUE_TOKEN = r"#(?:N\b|<digits>|\d+)"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_section(text):
    """'## 1. Parse arguments' up to the next '## ' heading ('' if absent)."""
    m = re.search(r"^## 1\. Parse arguments.*?(?=^## |\Z)", text, re.M | re.S)
    return m.group(0) if m else ""


def block(text, start):
    """From the line starting with `start` up to the next blank line or heading ('' if absent)."""
    m = re.search(r"^" + re.escape(start) + r".*?(?=\n\s*\n|\n#|\Z)", text, re.M | re.S)
    return m.group(0) if m else ""


def mode_list(section):
    """The '- **Mode:**' bullet and its indented sub-bullets ('' if absent)."""
    m = re.search(r"^- \*\*Mode:\*\*.*?(?=\n\S|\n\n|\Z)", section, re.M | re.S)
    return m.group(0) if m else ""


def units(text):
    """Sentences, also split at line ends (bullets)."""
    return [u for u in re.split(r"(?<=[.!?])\s+|\n", text) if u.strip()]


def has_unit_with(text, *patterns):
    """True if one sentence or line of `text` matches every pattern (case-insensitive)."""
    return any(all(re.search(p, u, re.I) for p in patterns) for u in units(text))


class InstalledSkillChecks:
    """Shared checks; mixed into one TestCase per installed skill."""
    skill = None

    @classmethod
    def setUpClass(cls):
        sb = SyncSandbox()
        try:
            r = sb.run()
            cls.sync_ok = (r.returncode == 0, r.stdout + r.stderr)
            path = sb.home_path("~/.claude/skills/%s/SKILL.md" % cls.skill)
            cls.text = _read(path) if os.path.isfile(path) else ""
        finally:
            sb.close()
        cls.section = parse_section(cls.text)

    # Harness guard (passes today): the sandbox sync itself must succeed.
    def test_sync_succeeds(self):
        self.assertTrue(self.sync_ok[0], self.sync_ok[1])

    # #58 / #60: resume or upgrade only when the only non-flag argument is a single #N.
    def test_resume_only_when_sole_non_flag_argument_is_issue(self):
        self.assertTrue(
            has_unit_with(self.section, r"\bonly\b", r"non-flag|other than (?:the )?flags",
                          ISSUE_TOKEN),
            "no parse rule saying the only non-flag argument must be a single #N:\n"
            + self.section)

    # #58 / #60: otherwise issue numbers in the description are references.
    def test_issue_numbers_in_description_are_references(self):
        self.assertTrue(
            has_unit_with(self.section, r"\breferences?\b", r"issue|#"),
            "no rule saying issue numbers in a description are references:\n" + self.section)


class DevMultiResumeModeTest(InstalledSkillChecks, unittest.TestCase):
    skill = "dev-multi"

    # #58 / #60: "Neither → MIXED for a new run".
    def test_neither_flag_means_mixed_only_for_new_run(self):
        self.assertRegex(mode_list(self.section), re.compile(r"new run", re.I))

    # #58 / #60: "on #N, the recorded mode".
    def test_neither_flag_on_resume_means_recorded_mode(self):
        self.assertRegex(mode_list(self.section), re.compile(r"recorded mode", re.I))

    # #58 / #60: the resuming paragraph changes the mode only when --fast or --rigor is given.
    def test_resume_changes_mode_only_with_explicit_flag(self):
        para = block(self.text, "**Resuming")
        self.assertTrue(has_unit_with(para, r"\bonly\b", r"--fast", r"--rigor"),
                        "resuming paragraph:\n" + para)

    # #58 / #60: the old "differs → update" rule is gone.
    def test_resume_no_longer_updates_mode_because_it_differs(self):
        old = "If the mode differs from the state file's, update it."
        self.assertFalse(old in self.text, "old rule still installed: " + old)

    # #58 / #60: upgrading from dev-single with no flag sets mode MIXED.
    def test_flagless_upgrade_from_dev_single_is_mixed(self):
        para = block(self.text, "**Upgrading from")
        self.assertTrue(has_unit_with(para, r"\bMIXED\b", FLAGLESS),
                        "upgrade paragraph:\n" + para)

    # #58 / #60: the --auto rules are unchanged. Characterization: passes before the change.
    def test_resume_without_auto_still_resets_auto(self):
        self.assertIn(
            "If the state has `auto: true` and this invocation lacks `--auto`, reset it to `false`",
            self.text)


class DevSingleResumeModeTest(InstalledSkillChecks, unittest.TestCase):
    skill = "dev-single"

    # #58 / #60: a flagless resume keeps the recorded mode.
    def test_resume_keeps_recorded_mode(self):
        self.assertRegex(block(self.text, "**Resuming"), re.compile(r"recorded mode", re.I))

    # #58 / #60: FAST stays the default for a new run only.
    def test_fast_is_default_only_for_new_run(self):
        self.assertTrue(has_unit_with(self.section, r"\bdefault\b", r"new run"),
                        "parse section:\n" + self.section)

    # #58 / #60: the old "differs → update" rule is gone.
    def test_resume_no_longer_updates_mode_because_it_differs(self):
        old = "If the state file's `mode` differs from this invocation's mode, update it."
        self.assertFalse(old in self.text, "old rule still installed: " + old)


class SmokeChecklistTest(unittest.TestCase):
    """#58 user story 21 / #60: three new checklist items for the live smoke run."""

    @classmethod
    def setUpClass(cls):
        cls.items = [l for l in _read(os.path.join(ROOT, "smoke", "CHECKLIST.md")).splitlines()
                     if l.lstrip().startswith("- [ ]")]

    def has_item(self, *patterns):
        return any(all(re.search(p, l, re.I) for p in patterns) for l in self.items)

    def test_flagless_resume_keeps_recorded_mode_item(self):
        self.assertTrue(self.has_item(FLAGLESS, r"recorded mode"))

    def test_flagless_upgrade_from_dev_single_is_mixed_item(self):
        self.assertTrue(self.has_item(FLAGLESS, r"dev-single", r"\bMIXED\b"))

    def test_description_with_issue_tokens_starts_new_run_item(self):
        self.assertTrue(self.has_item(ISSUE_TOKEN, r"\bdesc(?:ription)?\b", r"new run"))


if __name__ == "__main__":
    unittest.main()
