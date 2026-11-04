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


def check_vendors(root):
    """Skip unless every vendor clone exists at its locked commit: the sandbox links the
    real clones, so a sync must never need to fetch or check out in them. With
    DEVFLOW_REQUIRE_VENDORS=1 (CI), fail instead, so a run can't pass by skipping."""
    fail = unittest.SkipTest
    if os.environ.get("DEVFLOW_REQUIRE_VENDORS") == "1":
        fail = AssertionError
    with open(os.path.join(root, "manifest.json")) as f:
        vendors = json.load(f)["vendors"]
    with open(os.path.join(root, "vendor.lock")) as f:
        lock = json.load(f)
    for src, v in vendors.items():
        d = os.path.join(root, v["dir"])
        if not os.path.exists(os.path.join(d, ".git")):
            raise fail(
                "vendor clones missing: run ./sync.sh once in the devflow repo first")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d,
                              capture_output=True, text=True).stdout.strip()
        if head != lock.get(src):
            raise fail(
                f"{v['dir']} is at {head[:8] or '?'}, not {str(lock.get(src))[:8]} from vendor.lock: "
                "run ./sync.sh in the devflow repo first")


class SyncSandbox:
    def __init__(self, own_vendors=False):
        """own_vendors=False (default): the sandbox links the real `vendor/`.
        own_vendors=True: the sandbox gets an empty `vendor/` of its own and a manifest whose
        vendor urls are the real local clones (no network), so a sync clones them into the
        sandbox, or the test pre-clones them with `clone_vendors()`."""
        check_vendors(REAL_ROOT)
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
            if own_vendors:
                self._own_vendors()
            else:
                os.symlink(os.path.join(REAL_ROOT, "vendor"), os.path.join(self.repo, "vendor"))
        except Exception:
            self.close()
            raise
        self.local_file = os.path.join(self.repo, "devflow.local.json")

    def _own_vendors(self):
        path = os.path.join(self.repo, "manifest.json")
        with open(path, encoding="utf-8") as f:
            man = json.load(f)
        for v in man["vendors"].values():
            v["url"] = os.path.join(REAL_ROOT, v["dir"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(man, f, indent=2)
        os.makedirs(os.path.join(self.repo, "vendor"))

    def _env(self, env=None):
        e = {k: v for k, v in os.environ.items()
             if k != "XDG_CONFIG_HOME" and not k.startswith("GIT_CONFIG")}
        e["GIT_CONFIG_NOSYSTEM"] = "1"
        e["HOME"] = self.home
        for k, v in (env or {}).items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = v
        return e

    def run(self, *args, env=None):
        """Run sync.sh isolated from the runner's git and XDG settings; `env` overrides on top
        (a None value deletes the key)."""
        return subprocess.run(
            [os.path.join(self.repo, "sync.sh")] + list(args),
            cwd=self.repo, env=self._env(env), capture_output=True, text=True)

    def git(self, *args, cwd=None, check=True):
        """Run git with the same isolated environment as `run` (the sandbox HOME's
        `.gitconfig` is the global config)."""
        return subprocess.run(["git"] + list(args), cwd=cwd or self.repo, env=self._env(),
                              capture_output=True, text=True, check=check)

    def set_global_git_config(self, key, value):
        """Set `key` in the sandbox HOME's global git config."""
        self.git("config", "--global", key, value)

    def vendor_dirs(self):
        """{source: absolute path of the sandbox's clone of that vendor}."""
        with open(os.path.join(self.repo, "manifest.json"), encoding="utf-8") as f:
            vendors = json.load(f)["vendors"]
        return {src: os.path.join(self.repo, v["dir"]) for src, v in vendors.items()}

    def clone_vendors(self, git_config=None):
        """own_vendors only: clone every vendor from its manifest url at its vendor.lock commit,
        under the sandbox's git config plus `git_config` ({key: value}, passed as `git -c`)."""
        with open(os.path.join(self.repo, "manifest.json"), encoding="utf-8") as f:
            vendors = json.load(f)["vendors"]
        with open(os.path.join(self.repo, "vendor.lock"), encoding="utf-8") as f:
            lock = json.load(f)
        opts = []
        for k, v in (git_config or {}).items():
            opts += ["-c", f"{k}={v}"]
        for src, v in vendors.items():
            d = os.path.join(self.repo, v["dir"])
            self.git(*opts, "clone", "-q", "--no-checkout", v["url"], d)
            self.git(*opts, "checkout", "-q", lock[src], cwd=d)

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
