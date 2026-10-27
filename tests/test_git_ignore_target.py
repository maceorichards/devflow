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


class IgnoreTargetRobustnessTest(unittest.TestCase):
    """#37 (part of #34): a bad or unusable ignore target warns and never breaks the sync."""

    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)
        self.lines = expected_lines()
        self.home = self.sb.home
        self.tmp = self.sb.tmp

    def gitconfig(self, value):
        write(os.path.join(self.home, ".gitconfig"), core_block(value))

    def locked_setup(self, *args):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        locked = os.path.join(self.tmp, "locked")
        os.makedirs(locked)
        os.chmod(locked, 0o500)
        self.addCleanup(os.chmod, locked, 0o700)
        self.gitconfig(os.path.join(locked, "ignore"))
        return self.sb.run(*args)

    def ignore_lines(self, r):
        return [l for l in r.stdout.splitlines() if "git ignore" in l]

    def test_symlinked_target_stays_a_link(self):
        # Characterization: may already pass after Task 1.
        real = os.path.join(self.home, "dotfiles", "ignore")
        write(real, "node_modules\n")
        link = os.path.join(self.home, ".config", "git", "ignore")
        os.makedirs(os.path.dirname(link))
        os.symlink(real, link)
        self.sb.run()
        self.assertTrue(os.path.islink(link))
        got = read(real).splitlines()
        for l in ["node_modules"] + self.lines:
            self.assertIn(l, got)

    def test_missing_trailing_newline_is_respected(self):
        # Characterization: may already pass after Task 1.
        path = os.path.join(self.home, ".config", "git", "ignore")
        write(path, "node_modules")
        self.sb.run()
        got = read(path).splitlines()
        self.assertEqual(got[0], "node_modules")
        for l in self.lines:
            self.assertIn(l, got)

    def test_unwritable_target_returns_zero(self):
        r = self.locked_setup()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_unwritable_target_warns_with_lines(self):
        r = self.locked_setup()
        warn = [l for l in r.stdout.splitlines()
                if l.startswith("WARN git ignore: could not write ")]
        self.assertEqual(len(warn), 1, r.stdout + r.stderr)
        for l in self.lines:
            self.assertIn(l, warn[0])

    def test_unwritable_target_sync_still_completes(self):
        # Characterization: skills sync before the ignore step, so this passes pre-fix.
        self.locked_setup()
        self.assertTrue(self.sb.managed_skills("~/.claude/skills"))

    def test_relative_excludesfile_warns_and_writes_nothing(self):
        self.gitconfig("relative/ignore")
        r = self.sb.run()
        with self.subTest("exit code"):
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with self.subTest("warning"):
            self.assertTrue(any(
                l.startswith("WARN git ignore: core.excludesFile is relative (relative/ignore)")
                for l in r.stdout.splitlines()), r.stdout)
        for p in (os.path.join(self.sb.repo, "relative", "ignore"),
                  os.path.join(self.home, "relative", "ignore"),
                  os.path.join(self.home, ".config", "git", "ignore")):
            with self.subTest(path=p):
                self.assertFalse(os.path.exists(p))

    def test_unused_old_file_left_untouched(self):
        # Characterization: may already pass after Task 1.
        old = os.path.join(self.home, ".config", "git", "ignore")
        content = "# devflow (managed by somewhere)\n.devflow/\n"
        write(old, content)
        self.gitconfig("~/dotfiles/gitignore")
        self.sb.run()
        with self.subTest("old file unchanged"):
            self.assertEqual(read(old), content)
        with self.subTest("new file has lines"):
            got = read(os.path.join(self.home, "dotfiles", "gitignore")).splitlines()
            for l in self.lines:
                self.assertIn(l, got)

    def test_warning_keeps_single_ignore_status_line(self):
        self.sb.write_local(["claude"])
        r = self.locked_setup()
        found = self.ignore_lines(r)
        self.assertEqual(len(found), 1, r.stdout + r.stderr)
        out = r.stdout.splitlines()
        inst = [i for i, l in enumerate(out) if "instructions" in l]
        self.assertTrue(inst, r.stdout)
        self.assertGreater(out.index(found[0]), inst[0])


class IgnoreTargetFinalReviewTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)
        self.lines = expected_lines()
        self.home = self.sb.home

    def test_excludesfile_set_in_included_config_is_honored(self):
        write(os.path.join(self.home, ".gitconfig"), "[include]\n\tpath = ~/dotfiles/gitconfig\n")
        write(os.path.join(self.home, "dotfiles", "gitconfig"), core_block("~/dotfiles/gitignore"))
        self.sb.run()
        got = read(os.path.join(self.home, "dotfiles", "gitignore")).splitlines()
        for l in self.lines:
            self.assertEqual(got.count(l), 1, l)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config", "git", "ignore")))

    def test_undecodable_target_warns_and_is_left_unchanged(self):
        path = os.path.join(self.home, ".config", "git", "ignore")
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(b"\xff\xfe\x00bad")
        r = self.sb.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        warn = [l for l in r.stdout.splitlines() if l.startswith("WARN git ignore: could not read ")]
        self.assertEqual(len(warn), 1, r.stdout + r.stderr)
        for l in self.lines:
            self.assertIn(l, warn[0])
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"\xff\xfe\x00bad")


if __name__ == "__main__":
    unittest.main()
