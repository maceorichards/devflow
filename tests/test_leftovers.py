"""Acceptance tests for #35 (part of #34, group A): the clone path rendered at sync time,
the smoke-driver rule leaving the devflow section, and the repo's .gitignore rules."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests.harness import REAL_ROOT, SyncSandbox

START = "<!-- devflow:start"
END = "<!-- devflow:end -->"
# The marker line the template carried before #34 (global/claude-md-section.md, line 1).
OLD_HEADER = ("<!-- devflow:start (managed by ~/Documents/CUSTOM-SKILLS/devflow: "
              "edit global/claude-md-section.md there, then run sync.sh) -->")


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def start_lines(text):
    return [l for l in text.splitlines() if l.startswith(START)]


def names(path):
    """Regex matching `path` as a whole path (a following `/` is allowed, e.g. `<root>/global/...`)."""
    return re.escape(path) + r"(?![\w.-])"


class RealpathSandbox:
    """SyncSandbox run through real paths. On macOS the temp folder sits behind the
    /var -> /private/var symlink; running sync.sh by its real path with a real HOME
    leaves exactly one right answer for "the clone's root", whichever way the sync
    resolves it."""

    def __init__(self, home_is_repo_parent):
        self.sb = SyncSandbox()
        self.repo = os.path.realpath(self.sb.repo)
        tmp = os.path.realpath(self.sb.tmp)
        # HOME = the repo's parent gives `~/repo`; the default sandbox home is a sibling,
        # so the repo is outside HOME and the path stays absolute.
        self.home = tmp if home_is_repo_parent else os.path.realpath(self.sb.home)

    def run(self, *args):
        env = os.environ.copy()
        env["HOME"] = self.home
        # Keep the ignore file at today's default whatever the runner's environment (#37
        # resolves XDG_CONFIG_HOME and core.excludesFile; not under test here).
        env.pop("XDG_CONFIG_HOME", None)
        for k in list(env):
            if k.startswith("GIT_CONFIG"):
                del env[k]
        return subprocess.run([os.path.join(self.repo, "sync.sh")] + list(args),
                              cwd=self.repo, env=env, capture_output=True, text=True)

    def path(self, tilde):
        return os.path.join(self.home, tilde[2:])

    def close(self):
        self.sb.close()


class RenderedClonePathTest(unittest.TestCase):
    """#34 user stories 3 and 4: the header and the ignore comment name the user's clone."""

    def sandbox(self, home_is_repo_parent):
        sb = RealpathSandbox(home_is_repo_parent)
        self.addCleanup(sb.close)
        r = sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return sb

    def header(self, sb):
        lines = start_lines(read(sb.path("~/.claude/CLAUDE.md")))
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def ignore_comment(self, sb):
        lines = [l for l in read(sb.path("~/.config/git/ignore")).splitlines()
                 if l.startswith("# devflow")]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_header_names_clone_with_tilde_when_under_home(self):
        sb = self.sandbox(home_is_repo_parent=True)
        self.assertRegex(self.header(sb), names("~/repo"))

    def test_header_names_clone_absolute_when_outside_home(self):
        sb = self.sandbox(home_is_repo_parent=False)
        self.assertRegex(self.header(sb), names(sb.repo))

    def test_header_has_no_author_path(self):
        sb = self.sandbox(home_is_repo_parent=False)
        self.assertNotIn("CUSTOM-SKILLS", self.header(sb))

    def test_ignore_comment_names_clone_with_tilde_when_under_home(self):
        sb = self.sandbox(home_is_repo_parent=True)
        self.assertRegex(self.ignore_comment(sb), names("~/repo"))

    def test_ignore_comment_names_clone_absolute_when_outside_home(self):
        sb = self.sandbox(home_is_repo_parent=False)
        self.assertRegex(self.ignore_comment(sb), names(sb.repo))

    def test_ignore_comment_has_no_author_path(self):
        sb = self.sandbox(home_is_repo_parent=False)
        self.assertNotIn("CUSTOM-SKILLS", self.ignore_comment(sb))


class OldHeaderMigrationTest(unittest.TestCase):
    """#34 user story 5: an install with the old header is rewritten once, user text kept."""

    BEFORE = "# my rules\nkeep me before\n\n"
    AFTER = "\n# more of mine\nkeep me after\n"

    @classmethod
    def setUpClass(cls):
        cls.sb = RealpathSandbox(home_is_repo_parent=False)
        cls.md = cls.sb.path("~/.claude/CLAUDE.md")
        write(cls.md, cls.BEFORE + OLD_HEADER + "\n## devflow skills and workflows\nold body\n"
              + END + cls.AFTER)
        cls.result = cls.sb.run()
        cls.out = read(cls.md)

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    # characterization: an old header never made the sync fail
    def test_sync_succeeds(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)

    # characterization: marker detection already matches the `<!-- devflow:start` prefix
    def test_exactly_one_section_start(self):
        self.assertEqual(self.out.count(START), 1, self.out)

    def test_header_is_the_new_rendered_one(self):
        self.assertRegex(start_lines(self.out)[0], names(self.sb.repo))

    # characterization: text before the section was already preserved (#23)
    def test_text_before_section_unchanged(self):
        self.assertTrue(self.out.startswith(self.BEFORE + START), self.out)

    # characterization: text after the section was already preserved (#23)
    def test_text_after_section_unchanged(self):
        self.assertTrue(self.out.endswith(END + self.AFTER), self.out)


class SmokeRuleGoneTest(unittest.TestCase):
    """#34 user story 6: developing-devflow rules leave the installed devflow section."""

    @classmethod
    def setUpClass(cls):
        cls.sb = SyncSandbox()
        cls.result = cls.sb.run()
        cls.md = read(cls.sb.home_path("~/.claude/CLAUDE.md"))

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    def test_installed_section_has_no_smoke_driver_rule(self):
        self.assertNotIn("Smoke driver", self.md)

    # characterization: the other rules stay
    def test_installed_section_keeps_other_rules(self):
        self.assertIn("Never start a slash-only skill yourself", self.md)


class TemplateTest(unittest.TestCase):
    """#34 user stories 3 and 6: the template carries no author path and no smoke rule."""

    def template(self):
        return read(os.path.join(REAL_ROOT, "global", "claude-md-section.md"))

    def test_template_has_no_author_path(self):
        t = self.template()
        for bad in ("CUSTOM-SKILLS", "/Users/"):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, t)

    def test_template_has_no_smoke_driver_rule(self):
        self.assertNotIn("Smoke driver", self.template())


class RepoGitignoreTest(unittest.TestCase):
    """#34 user stories 9, 10 and 37: the repo's .gitignore, checked with git check-ignore in a
    throwaway repo so that nothing tracked or global can change the answer."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="devflow-gitignore-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        empty = os.path.join(self.tmp, "empty-excludes")
        write(empty, "")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("GIT_") and k != "XDG_CONFIG_HOME"}
        self.env.update(HOME=self.tmp, GIT_CONFIG_NOSYSTEM="1")
        self.git("init", "-q")
        self.git("config", "core.excludesFile", empty)
        shutil.copy2(os.path.join(REAL_ROOT, ".gitignore"), os.path.join(self.repo, ".gitignore"))
        self.target = os.path.join(self.tmp, "elsewhere")
        os.makedirs(self.target)

    def git(self, *args):
        return subprocess.run(["git"] + list(args), cwd=self.repo, env=self.env,
                              capture_output=True, text=True)

    def ignored(self, rel):
        r = self.git("check-ignore", "-q", rel)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        return r.returncode == 0

    def make_file(self, rel):
        write(os.path.join(self.repo, rel), "x\n")

    def make_dir(self, rel):
        os.makedirs(os.path.join(self.repo, rel))
        self.make_file(os.path.join(rel, "file"))

    def make_link(self, rel):
        p = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        os.symlink(self.target, p)

    def vendor_dirs(self):
        with open(os.path.join(REAL_ROOT, "manifest.json")) as f:
            return [v["dir"] for v in json.load(f)["vendors"].values()]

    def test_per_tool_instruction_files_ignored(self):
        for name in ("CLAUDE.md", "CLAUDE.local.md", "GEMINI.md"):
            with self.subTest(name=name):
                self.make_file(name)
                self.assertTrue(self.ignored(name))

    # characterization: `vendor/` already covers a real vendor directory
    def test_manifest_vendor_dirs_ignored_as_directories(self):
        dirs = self.vendor_dirs()
        self.assertTrue(dirs)
        for d in dirs:
            with self.subTest(dir=d):
                self.make_dir(d)
                self.assertTrue(self.ignored(d))

    # characterization: a symlink under a real `vendor/` folder is already covered by `vendor/`
    def test_manifest_vendor_dirs_ignored_as_symlinks(self):
        dirs = self.vendor_dirs()
        self.assertTrue(dirs)
        for d in dirs:
            with self.subTest(dir=d):
                self.make_link(d)
                self.assertTrue(self.ignored(d))

    def test_root_vendor_symlink_ignored(self):
        self.make_link("vendor")
        self.assertTrue(self.ignored("vendor"))

    # characterization: `vendor/` already matches a directory at any depth
    def test_nested_vendor_directory_ignored(self):
        self.make_dir("x/vendor")
        self.assertTrue(self.ignored("x/vendor"))

    # characterization: AGENTS.md was never ignored, and must stay tracked (#34 user story 32)
    def test_agents_md_not_ignored(self):
        self.make_file("AGENTS.md")
        self.assertFalse(self.ignored("AGENTS.md"))


if __name__ == "__main__":
    unittest.main()
