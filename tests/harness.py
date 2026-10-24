"""Sandbox for running ./sync.sh against a throwaway HOME and repo copy."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DIRS = ("lib", "owned", "patches", "global")
_FILES = ("manifest.json", "vendor.lock", "sync.sh")


class SyncSandbox:
    def __init__(self):
        for clone in ("superpowers", "mattpocock-skills"):
            if not os.path.exists(os.path.join(REAL_ROOT, "vendor", clone, ".git")):
                raise unittest.SkipTest(
                    "vendor clones missing: run ./sync.sh once in the devflow repo first")
        self.tmp = tempfile.mkdtemp(prefix="devflow-sandbox-")
        self.repo = os.path.join(self.tmp, "repo")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.repo)
        os.makedirs(self.home)
        try:
            ignore = shutil.ignore_patterns("__pycache__")
            for d in _DIRS:
                shutil.copytree(os.path.join(REAL_ROOT, d), os.path.join(self.repo, d), ignore=ignore)
            for f in _FILES:
                shutil.copy2(os.path.join(REAL_ROOT, f), os.path.join(self.repo, f))
            os.symlink(os.path.join(REAL_ROOT, "vendor"), os.path.join(self.repo, "vendor"))
        except Exception:
            self.close()
            raise
        self.local_file = os.path.join(self.repo, "devflow.local.json")

    def run(self, *args):
        env = os.environ.copy()
        env["HOME"] = self.home
        return subprocess.run(
            [os.path.join(self.repo, "sync.sh")] + list(args),
            cwd=self.repo, env=env, capture_output=True, text=True)

    def home_path(self, tilde_path):
        if tilde_path == "~":
            return self.home
        if tilde_path.startswith("~/"):
            return os.path.join(self.home, tilde_path[2:])
        return tilde_path

    def write_local(self, providers):
        with open(self.local_file, "w") as f:
            json.dump({"providers": providers}, f)

    def managed_skills(self, tilde_dir):
        d = self.home_path(tilde_dir)
        if not os.path.isdir(d):
            return set()
        return {n for n in os.listdir(d)
                if os.path.isfile(os.path.join(d, n, ".managed-by-devflow"))}

    def manifest_skill_names(self):
        with open(os.path.join(self.repo, "manifest.json")) as f:
            return {s["name"] for s in json.load(f)["skills"]}

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
