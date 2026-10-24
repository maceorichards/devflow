import os
import re
import unittest

from tests.harness import SyncSandbox

SKILLS = "~/.claude/skills"
# The three forms by which a skill told the agent to call the built-in code-review
FORBIDDEN = (
    "built-in `code-review`",
    "Skill tool with `code-review`",
    'Skill tool with "code-review"',
)


def read(path):
    with open(path) as f:
        return f.read()


class ReviewPathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = SyncSandbox()
        cls.sync_result = cls.sb.run()

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    def setUp(self):
        r = self.sync_result
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def skill_dir(self, name):
        return os.path.join(self.sb.home_path(SKILLS), name)

    def spec_review(self):
        return read(os.path.join(self.skill_dir("spec-review"), "SKILL.md"))

    # #23, user stories 29-32: the final review no longer calls the built-in code-review
    def test_no_skill_calls_builtin_code_review(self):
        for bad in FORBIDDEN:
            with self.subTest(forbidden=bad):
                offenders = []
                for name in sorted(self.sb.manifest_skill_names()):
                    root = self.skill_dir(name)
                    for dirpath, _, names in os.walk(root):
                        for n in names:
                            p = os.path.join(dirpath, n)
                            try:
                                text = read(p)
                            except (UnicodeDecodeError, OSError):
                                continue
                            if bad in text:
                                offenders.append("%s: %s" % (name, os.path.relpath(p, root)))
                self.assertEqual(offenders, [], "%r found in installed skills" % bad)

    # #23, spec-review gains a third Correctness axis
    def test_spec_review_has_correctness_section(self):
        text = self.spec_review()
        self.assertRegex(text, r"(?m)^## Correctness\b", "no '## Correctness' heading in spec-review")
        for axis in ("Standards", "Spec"):
            self.assertIn(axis, text)

    # #23: "The description changes from two-axis to three-axis"
    def test_spec_review_description_is_three_axis(self):
        text = self.spec_review()
        m = re.search(r"(?m)^description:.*$", text)
        self.assertIsNotNone(m, "spec-review has no description: line")
        self.assertIn("three-axis", m.group(0).lower())


if __name__ == "__main__":
    unittest.main()
