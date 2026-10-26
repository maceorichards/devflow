"""Acceptance tests for #37 (part of #34): the sync writes its ignore lines to the file git
really reads as the global excludes file, and names that file in its status line."""
import os
import unittest

from tests.harness import REAL_ROOT, SyncSandbox


def read(path):
    with open(path) as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def expected_lines():
    out = []
    for l in read(os.path.join(REAL_ROOT, "global", "git-ignore-lines")).splitlines():
        l = l.strip()
        if l and not l.startswith("#"):
            out.append(l)
    return out


def core_block(value):
    return "[core]\n\texcludesFile = %s\n" % value


class IgnoreTargetTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)
        self.lines = expected_lines()
        self.home = self.sb.home
        self.tmp = self.sb.tmp

    def gitconfig(self, value):
        write(os.path.join(self.home, ".gitconfig"), core_block(value))

    def assert_has_lines(self, path):
        self.assertTrue(os.path.exists(path), "missing " + path)
        got = read(path).splitlines()
        for l in self.lines:
            self.assertEqual(got.count(l), 1, "%r in %s" % (l, path))

    def test_excludesfile_tilde_value_gets_the_lines(self):
        self.gitconfig("~/dotfiles/gitignore")
        self.sb.run()
        self.assert_has_lines(os.path.join(self.home, "dotfiles", "gitignore"))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config", "git", "ignore")))

    def test_excludesfile_absolute_value_gets_the_lines(self):
        target = os.path.join(self.tmp, "elsewhere", "ignore")
        self.gitconfig(target)
        self.sb.run()
        self.assert_has_lines(target)

    def test_excludesfile_in_xdg_global_config_is_used(self):
        xdg = os.path.join(self.tmp, "xdg")
        write(os.path.join(xdg, "git", "config"), core_block("~/dotfiles/gitignore"))
        self.sb.run(env={"XDG_CONFIG_HOME": xdg})
        self.assert_has_lines(os.path.join(self.home, "dotfiles", "gitignore"))
        self.assertFalse(os.path.exists(os.path.join(xdg, "git", "ignore")))

    def test_git_config_global_env_is_honored(self):
        cfg = os.path.join(self.tmp, "custom.gitconfig")
        write(cfg, core_block("~/custom-ignore"))
        self.sb.run(env={"GIT_CONFIG_GLOBAL": cfg})
        self.assert_has_lines(os.path.join(self.home, "custom-ignore"))

    def test_xdg_config_home_used_without_excludesfile(self):
        xdg = os.path.join(self.tmp, "xdg")
        self.sb.run(env={"XDG_CONFIG_HOME": xdg})
        self.assert_has_lines(os.path.join(xdg, "git", "ignore"))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config", "git", "ignore")))

    def test_empty_xdg_config_home_falls_back_to_default(self):
        self.sb.run(env={"XDG_CONFIG_HOME": ""})
        self.assert_has_lines(os.path.join(self.home, ".config", "git", "ignore"))

    def test_default_when_nothing_is_set(self):
        # Characterization: today's default already holds; it must keep holding.
        self.sb.run()
        self.assert_has_lines(os.path.join(self.home, ".config", "git", "ignore"))

    def test_excludesfile_wins_over_xdg(self):
        self.gitconfig("~/dotfiles/gitignore")
        xdg = os.path.join(self.tmp, "xdg")
        self.sb.run(env={"XDG_CONFIG_HOME": xdg})
        self.assert_has_lines(os.path.join(self.home, "dotfiles", "gitignore"))
        self.assertFalse(os.path.exists(os.path.join(xdg, "git", "ignore")))

    def test_system_excludesfile_not_consulted(self):
        system = os.path.join(self.tmp, "system.gitconfig")
        system_ignore = os.path.join(self.tmp, "system-ignore")
        write(system, core_block(system_ignore))
        self.sb.run(env={"GIT_CONFIG_SYSTEM": system, "GIT_CONFIG_NOSYSTEM": None})
        self.assertFalse(os.path.exists(system_ignore))
        self.assert_has_lines(os.path.join(self.home, ".config", "git", "ignore"))

    def test_status_names_resolved_path(self):
        self.gitconfig("~/dotfiles/gitignore")
        r = self.sb.run()
        self.assertIn("added to git ignore ~/dotfiles/gitignore: " + ", ".join(self.lines), r.stdout)

    def test_dry_run_names_path_and_writes_nothing(self):
        self.gitconfig("~/dotfiles/gitignore")
        r = self.sb.run("--dry-run")
        self.assertIn("would add to git ignore ~/dotfiles/gitignore: ", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.home, "dotfiles", "gitignore")))

    def test_resync_reports_present_and_adds_nothing(self):
        self.sb.run()
        r = self.sb.run()
        self.assertIn("git ignore lines present in ~/.config/git/ignore", r.stdout)
        self.assert_has_lines(os.path.join(self.home, ".config", "git", "ignore"))

    def test_comment_written_once_in_resolved_target(self):
        self.gitconfig("~/dotfiles/gitignore")
        self.sb.run()
        self.sb.run()
        path = os.path.join(self.home, "dotfiles", "gitignore")
        self.assertTrue(os.path.exists(path), "missing " + path)
        got = read(path).splitlines()
        self.assertEqual(len([l for l in got if l.startswith("# devflow")]), 1)

    def test_harness_ignores_runner_xdg(self):
        # Characterization until the sync reads XDG_CONFIG_HOME: it then guards the harness
        # isolation (the runner's variable must not reach the sync).
        old = os.environ.get("XDG_CONFIG_HOME")
        runner = os.path.join(self.tmp, "runner-xdg")
        os.environ["XDG_CONFIG_HOME"] = runner
        try:
            self.sb.run()
        finally:
            if old is None:
                del os.environ["XDG_CONFIG_HOME"]
            else:
                os.environ["XDG_CONFIG_HOME"] = old
        self.assert_has_lines(os.path.join(self.home, ".config", "git", "ignore"))
        self.assertFalse(os.path.exists(os.path.join(runner, "git", "ignore")))


if __name__ == "__main__":
    unittest.main()
