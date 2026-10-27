"""Acceptance tests for #38 (#34 part D): the smoke kit docs and DESIGN.md entry 16.

Black-box: the repo's files are read directly, and the merged driver is run only
through `python3 -I smoke/drive.py <sub> --help` to catch drift between the
README and the real CLI. Prose quality is left to review.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVE = os.path.join(ROOT, "smoke", "drive.py")

# #36: the merged driver's subcommands.
SUBCOMMANDS = ("init", "send", "step", "loop")


def path(name):
    return os.path.join(ROOT, name)


def read(name):
    with open(path(name)) as f:
        return f.read()


def section(text, number):
    """Text from the '## N.' heading to the next '## ' heading ('' if absent)."""
    m = re.search(r"^## %d\..*?(?=^## |\Z)" % number, text, re.M | re.S)
    return m.group(0) if m else ""


def driver_help():
    """Concatenated --help output of every driver subcommand."""
    out = []
    for sub in SUBCOMMANDS:
        p = subprocess.run(
            [sys.executable, "-I", DRIVE, sub, "--help"],
            cwd=ROOT, capture_output=True, text=True,
        )
        out.append(p.stdout)
    return "\n".join(out)


class DocTestCase(unittest.TestCase):
    doc = None

    def text(self):
        if not os.path.isfile(path(self.doc)):
            self.fail("%s does not exist" % self.doc)
        return read(self.doc)


class SmokeReadmeTest(DocTestCase):
    """#38 / #34 user story 38: smoke/README.md explains and walks through a smoke run."""

    doc = "smoke/README.md"

    def test_readme_exists(self):
        self.assertTrue(os.path.isfile(path(self.doc)), "smoke/README.md does not exist")

    def test_readme_explains_what_a_smoke_run_is(self):
        self.assertIn("smoke run", self.text())

    def test_readme_states_the_cost(self):
        self.assertIn("cost", self.text().lower())

    def test_readme_keeps_bypass_to_a_throwaway_repo(self):
        # #34 user story 38: bypass permissions only in a throwaway repo
        paras = re.split(r"\n\s*\n", self.text())
        self.assertTrue(
            any("bypass" in p.lower() and "throwaway" in p.lower() for p in paras),
            "no paragraph mentions both bypass and throwaway",
        )

    def test_readme_lists_gh_as_a_prerequisite(self):
        self.assertIn("gh", re.findall(r"[\w-]+", self.text()))

    def test_readme_walkthrough_uses_drive_init(self):
        self.assertIn("drive.py init", self.text())

    def test_readme_walkthrough_gives_setup_devflow_skills(self):
        # #34 user story 39: init prints the /setup-devflow-skills answers to give
        self.assertIn("/setup-devflow-skills", self.text())

    def test_readme_walkthrough_uses_drive_send(self):
        self.assertIn("drive.py send", self.text())

    def test_readme_walkthrough_uses_drive_loop(self):
        self.assertIn("drive.py loop", self.text())

    def test_readme_documents_agent_option(self):
        self.assertIn("--agent", self.text())

    def test_readme_documents_stand_in_option(self):
        self.assertIn("--stand-in", self.text())

    def test_readme_explains_adding_an_agent_via_agents_json(self):
        # #34 user story 45: adding an agent means adding one entry to the table
        self.assertIn("agents.json", self.text())

    def test_readme_says_findings_become_issues(self):
        self.assertIn("issue", self.text().lower())

    def test_readme_names_only_real_subcommands(self):
        # #38: every `drive.py <word>` the README names is a merged driver subcommand (#36)
        named = set(re.findall(r"drive\.py\s+([a-z][\w-]*)", self.text()))
        self.assertTrue(named and named <= set(SUBCOMMANDS),
                        "README drive.py subcommands %r, driver has %r" % (sorted(named), SUBCOMMANDS))

    def test_readme_names_only_options_the_driver_accepts(self):
        # #38: every --option on a README line that runs drive.py appears in some
        # subcommand's real --help output
        lines = [l for l in self.text().splitlines() if "drive.py" in l]
        named = set(re.findall(r"(?<![\w-])--[a-z][\w-]*", "\n".join(lines)))
        accepted = set(re.findall(r"(?<![\w-])--[a-z][\w-]*", driver_help()))
        self.assertTrue(lines and named <= accepted,
                        "README driver options not accepted: %r" % sorted(named - accepted))


class SmokeChecklistTest(DocTestCase):
    """#38 / #34 user story 48: smoke/CHECKLIST.md matches current behavior."""

    doc = "smoke/CHECKLIST.md"

    def test_checklist_exists(self):
        self.assertTrue(os.path.isfile(path(self.doc)), "smoke/CHECKLIST.md does not exist")

    def test_checklist_has_no_claude_docs_path(self):
        self.assertNotIn(".claude/docs", self.text())

    def test_checklist_has_no_claude_local_md(self):
        self.assertNotIn("CLAUDE.local.md", self.text())

    def test_checklist_has_no_code_review_command(self):
        self.assertNotIn("/code-review", self.text())

    def test_checklist_uses_devflow_folder(self):
        self.assertIn(".devflow/", self.text())

    def test_checklist_checks_spec_review(self):
        self.assertIn("spec-review", self.text())

    def test_checklist_checks_base_branch_question(self):
        self.assertIn("base branch", self.text().lower())


class StandInDocTest(DocTestCase):
    """#38 / #34: smoke/STAND-IN.md is public-safe and matches the fixture (#36)."""

    doc = "smoke/STAND-IN.md"

    def test_stand_in_exists(self):
        self.assertTrue(os.path.isfile(path(self.doc)), "smoke/STAND-IN.md does not exist")

    def test_stand_in_has_no_username(self):
        self.assertNotIn("maceorichards", self.text())

    def test_stand_in_has_no_home_path(self):
        self.assertNotIn("/Users/", self.text())

    def test_stand_in_has_no_toolbox(self):
        self.assertNotIn("toolbox", self.text())

    def test_stand_in_has_no_uv_run(self):
        self.assertNotIn("uv run", self.text())

    def test_stand_in_names_fixture_package_tally(self):
        self.assertIn("tally", self.text())

    def test_stand_in_names_unittest_command(self):
        self.assertIn("python3 -m unittest", self.text())


class DesignSmokeTest(unittest.TestCase):
    """#38 / #34: DESIGN.md says "smoke run" and gains entry 16."""

    def design(self):
        return read("DESIGN.md")

    def test_design_never_says_smoke_test(self):
        hits = [l for l in self.design().splitlines() if "smoke test" in l.lower()]
        self.assertEqual(hits, [], "DESIGN.md still says 'smoke test'")

    def test_design_says_smoke_run(self):
        # Characterization: DESIGN.md already says "smoke run" (entry 12); #38 must keep it.
        self.assertIn("smoke run", self.design())

    def test_design_links_smoke_readme(self):
        self.assertIn("smoke/README.md", re.findall(r"\]\(([^)]*)\)", self.design()))

    def test_design_has_entry_16(self):
        heads = [l for l in self.design().splitlines() if l.startswith("## 16.")]
        self.assertTrue(heads, "no '## 16.' heading in DESIGN.md")

    def test_design_entry_16_mentions_contributor_instructions(self):
        self.assertIn("contributor instructions", section(self.design(), 16))

    def test_design_entry_16_mentions_devflow_section(self):
        self.assertIn("devflow section", section(self.design(), 16))

    def test_design_entry_16_mentions_smoke(self):
        self.assertIn("smoke", section(self.design(), 16))

    def test_design_entry_16_records_rejected_alternatives(self):
        self.assertIn("Rejected", section(self.design(), 16))


if __name__ == "__main__":
    unittest.main()
