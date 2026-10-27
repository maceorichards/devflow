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


def named_section(text, title):
    """Text from '## <title>' to the next '## ' heading ('' if absent)."""
    m = re.search(r"^## %s\s*$.*?(?=^## |\Z)" % re.escape(title), text, re.M | re.S)
    return m.group(0) if m else ""


def paragraphs(text):
    return re.split(r"\n\s*\n|\n(?=\s*[-*] )", text)


class ReadmeFirstRunTest(unittest.TestCase):
    """#39 (#34 user stories 22-31): the README opens with public framing and a quickstart."""

    def quickstart(self):
        return named_section(read("README.md"), "Quickstart")

    def test_intro_says_opinionated(self):
        intro = read("README.md").split("\n## ", 1)[0].lower()
        self.assertIn("opinionated", intro)

    def test_intro_says_fork(self):
        intro = read("README.md").split("\n## ", 1)[0].lower()
        self.assertIn("fork", intro)

    def test_quickstart_section_exists(self):
        self.assertTrue(self.quickstart(), "no '## Quickstart' section")

    def test_quickstart_comes_before_workflows(self):
        readme = read("README.md")
        self.assertIn("## Quickstart", readme)
        self.assertLess(readme.find("## Quickstart"), readme.find("## Workflows"))

    def test_quickstart_names_prerequisites(self):
        qs = self.quickstart()
        for s in ("Python 3.9", "git", "GitHub"):
            with self.subTest(s=s):
                self.assertIn(s, qs)

    def test_quickstart_names_gh_as_a_word(self):
        self.assertRegex(self.quickstart(), r"\bgh\b")

    def test_quickstart_steps_in_order(self):
        qs = self.quickstart()
        clone = qs.find("git clone")
        dry = qs.find("./sync.sh --dry-run")
        bare = re.search(r"^[ \t`$>]*\./sync\.sh[ \t`]*$", qs[max(dry, 0):], re.M) if dry >= 0 else None
        setup = qs.find("/setup-devflow-skills")
        self.assertTrue(0 <= clone < dry, "git clone must come before ./sync.sh --dry-run")
        self.assertTrue(bare, "no bare ./sync.sh line after the dry run")
        self.assertLess(dry + bare.start(), setup)

    def test_quickstart_names_files_the_sync_edits(self):
        qs = self.quickstart().lower()
        for s in ("skills folder", "instructions file", "ignore"):
            with self.subTest(s=s):
                self.assertIn(s, qs)

    def test_quickstart_says_system_excludes_file_is_not_consulted(self):
        paras = paragraphs(self.quickstart())
        self.assertTrue(
            any("core.excludesFile" in p and "system" in p for p in paras),
            "no paragraph or list item has core.excludesFile with 'system'")

    def test_readme_tells_users_to_fork_and_edit_manifest(self):
        # characterization: passes today (an existing paragraph already says both); must survive #39
        paras = re.split(r"\n\s*\n", read("README.md"))
        self.assertTrue(any("fork" in p.lower() and "manifest.json" in p for p in paras),
                        "no paragraph has fork with manifest.json")

    def test_contributing_section_exists(self):
        self.assertTrue(named_section(read("README.md"), "Contributing"), "no '## Contributing' section")

    def test_contributing_links_agents_md(self):
        self.assertIn("](AGENTS.md)", named_section(read("README.md"), "Contributing"))

    def test_contributing_links_smoke_readme(self):
        self.assertIn("](smoke/README.md)", named_section(read("README.md"), "Contributing"))

    def test_reference_sections_kept(self):
        # characterization: these sections exist before #39 and must survive it
        readme = read("README.md")
        for h in ("Workflows", "Providers", "Tiers", "Repo layout", "Commands"):
            with self.subTest(h=h):
                self.assertTrue(named_section(readme, h), "missing '## %s'" % h)


class CiWorkflowTest(unittest.TestCase):
    """#39 (#34 user stories 22-31): CI runs the unit tests and a fresh install."""

    def ci(self):
        path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
        return open(path).read() if os.path.exists(path) else ""

    def test_workflow_file_exists(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, ".github", "workflows", "ci.yml")))

    def test_triggers_on_pull_request(self):
        self.assertIn("pull_request", self.ci())

    def test_triggers_on_push(self):
        self.assertRegex(self.ci(), r"(?m)^\s*push\s*:")

    def test_push_branches_are_develop_and_main(self):
        m = re.search(r"(?ms)^\s*push\s*:.*?branches\s*:(.*?)(?=^\S|^\s*\w+\s*:\s*$|\Z)", self.ci())
        block = m.group(1) if m else ""
        for b in ("develop", "main"):
            with self.subTest(branch=b):
                self.assertIn(b, block)

    def test_has_unit_job(self):
        self.assertRegex(self.ci(), r"(?m)^  unit:")

    def test_has_fresh_install_job(self):
        self.assertRegex(self.ci(), r"(?m)^  fresh-install:")

    def test_matrix_covers_ubuntu_and_macos(self):
        ci = self.ci()
        for s in ("ubuntu-latest", "macos-latest"):
            with self.subTest(s=s):
                self.assertIn(s, ci)

    def test_matrix_covers_python_3_9_and_3_x(self):
        ci = self.ci()
        self.assertRegex(ci, r"""['"]?3\.9['"]?""")
        self.assertRegex(ci, r"""['"]3\.x['"]|\b3\.x\b""")

    def test_requires_vendors(self):
        self.assertRegex(self.ci(), r"DEVFLOW_REQUIRE_VENDORS\s*:\s*['\"]?1['\"]?")

    def test_runs_sync_dry_run(self):
        self.assertIn("./sync.sh --dry-run", self.ci())

    def test_runs_unittest(self):
        self.assertIn("python3 -m unittest", self.ci())
