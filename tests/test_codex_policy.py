import json
import os
import re
import unittest

from tests.harness import SyncSandbox

SKILLS = "~/.claude/skills"


def read(path):
    with open(path) as f:
        return f.read()


class CodexPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = SyncSandbox()
        r = cls.sb.run()
        if r.returncode != 0:
            cls.sb.close()
            raise AssertionError("sync failed: " + r.stdout + r.stderr)
        with open(os.path.join(cls.sb.repo, "manifest.json")) as f:
            cls.skills = json.load(f)["skills"]

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    def yaml_path(self, name):
        return os.path.join(self.sb.home_path(SKILLS), name, "agents", "openai.yaml")

    def names(self, tiers):
        return [s["name"] for s in self.skills if s["tier"] in tiers]

    # #23, user story 26: slash-tier skills are never implicitly invoked by Codex
    def test_slash_tier_skills_disallow_implicit_invocation(self):
        slash = self.names({"slash"})
        self.assertTrue(slash)
        for name in slash:
            path = self.yaml_path(name)
            self.assertTrue(os.path.isfile(path), name + ": agents/openai.yaml missing")
            lines = read(path).splitlines()
            idx = [i for i, l in enumerate(lines) if l.startswith("policy:")]
            self.assertTrue(idx, name + ": no policy: block")
            tail = lines[idx[0] + 1:]
            self.assertTrue(
                any(re.match(r"^\s+allow_implicit_invocation:\s*false\s*$", l) for l in tail),
                name + ": allow_implicit_invocation: false missing under policy:")

    # #23, user story 27: sub and auto tiers carry no policy block
    def test_sub_and_auto_tier_skills_have_no_policy(self):
        checked = 0
        for name in self.names({"sub", "auto"}):
            path = self.yaml_path(name)
            if not os.path.isfile(path):
                continue
            checked += 1
            text = read(path)
            self.assertFalse(re.search(r"^policy:", text, re.M), name + ": has policy:")
            self.assertNotIn("allow_implicit_invocation", text, name)
        self.assertTrue(checked)

    # #23, user story 27: the rest of upstream's yaml (interface) is kept
    def test_upstream_interface_block_kept(self):
        text = read(self.yaml_path("grilling"))
        self.assertIn("interface:", text)
        self.assertIn("display_name:", text)

    # #23, user story 28: rewrites and prefix strip apply to .yaml files
    def test_setup_display_name_has_no_matt_pocock(self):
        text = read(self.yaml_path("setup-devflow-skills"))
        self.assertIn("display_name:", text)
        self.assertNotIn("Matt Pocock", text)


if __name__ == "__main__":
    unittest.main()
