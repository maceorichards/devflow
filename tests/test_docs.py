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
