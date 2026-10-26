"""Acceptance tests for #29: docs (DESIGN.md entry 15, README, SKILLS.md) cover any provider."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(name):
    with open(os.path.join(ROOT, name)) as f:
        return f.read()


def section(text, number):
    """Text from the '## N.' heading to the next '## ' heading ('' if absent)."""
    m = re.search(r"^## %d\..*?(?=^## |\Z)" % number, text, re.M | re.S)
    return m.group(0) if m else ""


class DocsTest(unittest.TestCase):
    def test_design_has_any_provider_entry(self):
        # #23 Docs: DESIGN.md gains entry 15 on any-provider support; user story 33
        heads = [l for l in read("DESIGN.md").splitlines() if l.startswith("## 15.")]
        self.assertTrue(heads, "no '## 15.' heading in DESIGN.md")
        self.assertIn("any provider", heads[0].lower())

    def test_design_old_entries_no_longer_current(self):
        # #23 Docs: entries 5, 7 and 8 are amended for .devflow/ and the dropped block
        design = read("DESIGN.md")
        for n in (5, 7, 8):
            sec = section(design, n)
            self.assertTrue(sec, "entry %d missing" % n)
            if "CLAUDE.local.md" in sec:
                self.assertIn(".devflow/", sec, "entry %d mentions CLAUDE.local.md without .devflow/" % n)
            if ".claude/docs/" in sec:
                self.assertIn(".devflow/", sec, "entry %d still has .claude/docs/ without .devflow/" % n)

    def test_readme_documents_providers(self):
        # #23 user story 24: README documents provider selection
        readme = read("README.md")
        for s in ("./sync.sh providers", "claude", "codex", "gemini", "cursor", "devflow.local.json"):
            self.assertIn(s, readme)

    def test_readme_documents_devflow_folder_and_migration(self):
        # #23 user story 34: README explains .devflow/ and the migration from .claude/docs
        readme = read("README.md")
        for s in (".devflow/", "mv .claude/docs .devflow", "Agent skills"):
            self.assertIn(s, readme)

    def test_readme_documents_cursor_caveat(self):
        # #23 user story 24: Cursor also reads Claude/Codex skill folders, so duplicates can appear
        paras = re.split(r"\n\s*\n", read("README.md"))
        self.assertTrue(
            any("Cursor" in p and "Claude" in p and "Codex" in p for p in paras),
            "no paragraph mentions Cursor with Claude and Codex",
        )

    def test_skills_md_matches_manifest_descriptions(self):
        # #23 Docs: SKILLS.md matches the manifest (three-axis spec-review, no CLAUDE.local.md block)
        skills = read("SKILLS.md")
        self.assertIn("three-axis", skills.lower())
        self.assertNotIn("CLAUDE.local.md", skills)


def read_if_exists(name):
    path = os.path.join(ROOT, name)
    return read(name) if os.path.exists(path) else ""


class ContributorInstructionsTest(unittest.TestCase):
    """#35 (#34 user stories 32-36): a tracked AGENTS.md carries the contributor rules."""

    def agents(self):
        return read_if_exists("AGENTS.md")

    def test_agents_md_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "AGENTS.md")))

    def test_agents_md_has_smoke_driver_rule(self):
        # #34 user story 34: generalized to a headless child agent session, only in the
        # throwaway smoke repo, never in any other repo or the agent's own session
        text = self.agents().lower()
        for s in ("headless child agent session", "throwaway smoke repo", "other repo", "own session"):
            with self.subTest(s=s):
                self.assertIn(s, text)

    def test_agents_md_has_test_command(self):
        # #34 user story 33
        self.assertIn("python3 -m unittest", self.agents())

    def test_agents_md_has_patch_edit_save_flow(self):
        # #34 user story 33: patches change through `sync.sh edit` / `save`
        text = self.agents()
        with self.subTest(step="edit"):
            self.assertIn("sync.sh edit", text)
        with self.subTest(step="save"):
            self.assertRegex(text, r"sync\.sh save|`?edit`?\s*/\s*`?save")

    def test_agents_md_forbids_editing_installed_skills(self):
        # #34 user story 33: "never edit an installed skill" (wording as in the README's rule)
        self.assertRegex(self.agents(), r"(?i)(never|don't|do not)\s+edit[^.\n]*installed")

    def test_agents_md_has_claude_note(self):
        # #34 user story 35
        self.assertIn("@AGENTS.md", self.agents())

    def test_agents_md_has_gemini_note(self):
        # #34 user story 36
        self.assertIn("context.fileName", self.agents())


class LicenseTest(unittest.TestCase):
    """#35 (#34 user stories 1 and 2): MIT license and upstream notices."""

    def test_license_is_mit(self):
        self.assertIn("MIT License", read_if_exists("LICENSE"))

    def test_license_copyright_line(self):
        # #34 Implementation Decisions: "Copyright (c) 2026 Maceo Richards"
        self.assertIn("Copyright (c) 2026 Maceo Richards", read_if_exists("LICENSE"))

    def test_notices_name_both_upstreams(self):
        text = read_if_exists("THIRD_PARTY_NOTICES.md")
        for s in ("obra/superpowers", "Jesse Vincent", "mattpocock/skills", "Matt Pocock"):
            with self.subTest(s=s):
                self.assertIn(s, text)

    def test_notices_carry_mit_permission_text(self):
        self.assertIn("Permission is hereby granted, free of charge",
                      read_if_exists("THIRD_PARTY_NOTICES.md"))

    def test_notices_name_derived_parts(self):
        # #34 Implementation Decisions: the patches, and `tdd`, forked from Matt's
        text = read_if_exists("THIRD_PARTY_NOTICES.md")
        for s in ("patches", "tdd"):
            with self.subTest(s=s):
                self.assertIn(s, text)
