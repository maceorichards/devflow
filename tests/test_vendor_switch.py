"""Acceptance tests for #39 (#34 user stories 22-31): DEVFLOW_REQUIRE_VENDORS turns the
vendor skip in check_vendors into a failure, so CI cannot pass by skipping everything."""
import json
import os
import subprocess
import tempfile
import unittest

from tests.harness import check_vendors

VAR = "DEVFLOW_REQUIRE_VENDORS"
OTHER_SHA = "0" * 40


def make_root(tmp, clone):
    """Root with one vendor 'x'; clone=None leaves it missing, else a git repo at another sha."""
    with open(os.path.join(tmp, "manifest.json"), "w") as f:
        json.dump({"vendors": {"x": {"url": "unused", "dir": "vendor/x"}}}, f)
    with open(os.path.join(tmp, "vendor.lock"), "w") as f:
        json.dump({"x": OTHER_SHA}, f)
    if clone:
        d = os.path.join(tmp, "vendor", "x")
        os.makedirs(d)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "c"], cwd=d, check=True, env=env)
    return tmp


def outcome(root, value):
    """Exception raised by check_vendors(root) with the variable set to value (None = unset)."""
    old = os.environ.get(VAR)
    try:
        if value is None:
            os.environ.pop(VAR, None)
        else:
            os.environ[VAR] = value
        try:
            check_vendors(root)
        except BaseException as e:  # SkipTest included
            return e
        return None
    finally:
        if old is None:
            os.environ.pop(VAR, None)
        else:
            os.environ[VAR] = old


class VendorSwitchTest(unittest.TestCase):
    def root(self, clone):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return make_root(tmp.name, clone)

    def assert_fails(self, e):
        self.assertIsNotNone(e, "check_vendors did not raise")
        self.assertNotIsInstance(e, unittest.SkipTest)

    def test_required_missing_clone_fails(self):
        self.assert_fails(outcome(self.root(False), "1"))

    def test_required_drifted_clone_fails(self):
        self.assert_fails(outcome(self.root(True), "1"))

    def test_required_missing_clone_message_says_run_sync(self):
        # characterization: passes today via the SkipTest message; must hold for the new exception
        e = outcome(self.root(False), "1")
        self.assertIsNotNone(e)
        self.assertIn("./sync.sh", str(e))

    def test_required_drifted_clone_message_says_run_sync(self):
        # characterization: passes today via the SkipTest message; must hold for the new exception
        e = outcome(self.root(True), "1")
        self.assertIsNotNone(e)
        self.assertIn("./sync.sh", str(e))

    def test_unset_missing_clone_skips(self):
        # characterization: today's behavior, kept when the variable is absent
        self.assertIsInstance(outcome(self.root(False), None), unittest.SkipTest)

    def test_unset_drifted_clone_skips(self):
        # characterization
        self.assertIsInstance(outcome(self.root(True), None), unittest.SkipTest)

    def test_zero_missing_clone_skips(self):
        # characterization
        self.assertIsInstance(outcome(self.root(False), "0"), unittest.SkipTest)

    def test_zero_drifted_clone_skips(self):
        # characterization
        self.assertIsInstance(outcome(self.root(True), "0"), unittest.SkipTest)


if __name__ == "__main__":
    unittest.main()
