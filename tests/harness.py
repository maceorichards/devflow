"""Sandbox for running ./sync.sh against a throwaway HOME and repo copy."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DIRS = ("lib", "owned", "patches", "global")
_FILES = ("manifest.json", "vendor.lock", "sync.sh")

IS_WINDOWS = os.name == "nt"


# --- platform support --------------------------------------------------------------------
# The suite runs on Linux, macOS and Windows (from Git Bash, as the README says). Windows
# differs in four ways the tests meet: creating symlinks needs Developer Mode or admin, a
# script can't be executed directly (only .exe/.com), chmod can't make a folder read-only,
# and git leaves its object files read-only, so a plain rmtree fails on a clone.

def _probe_symlinks():
    d = tempfile.mkdtemp(prefix="devflow-symlink-probe-")
    try:
        os.symlink(d, os.path.join(d, "link"), target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        return False
    finally:
        shutil.rmtree(d, ignore_errors=True)


CAN_SYMLINK = _probe_symlinks()

requires_symlinks = unittest.skipUnless(
    CAN_SYMLINK, "needs symlinks (on Windows: turn on Developer Mode, or run as admin)")


def ignores_permissions():
    """True where a read-only folder can still be written to: root, and Windows, where
    chmod only toggles a file's read-only flag and has no effect on folders."""
    return IS_WINDOWS or (hasattr(os, "geteuid") and os.geteuid() == 0)


requires_posix_permissions = unittest.skipIf(
    ignores_permissions(), "needs read-only folders (POSIX, not root)")


def set_home(env, home):
    """Point `~` at `home` in the environment dict `env`, for every process a sync starts.
    Python on Windows resolves ~ from USERPROFILE and never reads HOME, so setting HOME alone
    would let sync.py write to the runner's real profile while the test looks in `home`."""
    env["HOME"] = home
    if IS_WINDOWS:
        env["USERPROFILE"] = home
        env.pop("HOMEDRIVE", None)
        env.pop("HOMEPATH", None)
    return env


def link_dir(target, link):
    """Make `link` point at the folder `target`: a symlink, or on Windows without symlink
    rights a directory junction, which needs no privilege and which rmtree never follows."""
    if CAN_SYMLINK:
        os.symlink(target, link, target_is_directory=True)
    elif IS_WINDOWS:
        import _winapi
        _winapi.CreateJunction(os.path.abspath(target), os.path.abspath(link))
    else:
        raise unittest.SkipTest("cannot create symlinks here")


def rmtree(path):
    """shutil.rmtree that also removes read-only files (git objects on Windows)."""
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if not os.path.lexists(path):
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=onerror)
    else:
        shutil.rmtree(path, onerror=onerror)


def _git_bash():
    """Git for Windows' bash: the bash next to the git on PATH, so a WSL `bash.exe` in
    System32 is never picked up. Falls back to whatever `bash` is on PATH."""
    git = shutil.which("git")
    if git:
        d = os.path.dirname(os.path.realpath(git))
        for _ in range(4):
            for cand in (os.path.join(d, "bin", "bash.exe"),
                         os.path.join(d, "usr", "bin", "bash.exe")):
                if os.path.isfile(cand):
                    return cand
            d = os.path.dirname(d)
    return shutil.which("bash") or "bash"


def script_argv(path):
    """argv that runs the shell script at `path`: the script itself on POSIX, through Git
    Bash on Windows, which can't execute a script directly."""
    return [_git_bash(), path] if IS_WINDOWS else [path]


def install_python_command(script, bin_dir, name):
    """Make the Python file `script` runnable as the command `name` from `bin_dir`.

    POSIX: a copy named `name`, made executable (the script has a shebang). Windows:
    `name.exe`, the console launcher pip uses for its own commands with the script zipped
    behind it, so argv (newlines included) reaches the script intact and sys.argv[0] ends
    in `name.exe`."""
    if not IS_WINDOWS:
        dest = os.path.join(bin_dir, name)
        shutil.copy(script, dest)
        os.chmod(dest, 0o755)
        return dest
    import io
    import platform
    import zipfile
    try:
        from pip._vendor.distlib import scripts as _distlib_scripts
    except ImportError:
        raise unittest.SkipTest("needs pip's console launcher to fake a command on Windows")
    arch = "t64-arm.exe" if platform.machine().lower() in ("arm64", "aarch64") else (
        "t64.exe" if sys.maxsize > 2 ** 32 else "t32.exe")
    with open(os.path.join(os.path.dirname(_distlib_scripts.__file__), arch), "rb") as f:
        launcher = f.read()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        with open(script, encoding="utf-8") as f:
            z.writestr("__main__.py", f.read())
    exe = sys.executable
    shebang = ('#!"%s"\r\n' % exe if " " in exe else "#!%s\r\n" % exe).encode("utf-8")
    dest = os.path.join(bin_dir, name + ".exe")
    with open(dest, "wb") as f:
        f.write(launcher + shebang + buf.getvalue())
    return dest


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
                link_dir(os.path.join(REAL_ROOT, "vendor"), os.path.join(self.repo, "vendor"))
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
        set_home(e, self.home)
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
            script_argv(os.path.join(self.repo, "sync.sh")) + list(args),
            cwd=self.repo, env=self._env(env), capture_output=True, text=True,
            encoding="utf-8")  # sync.py runs with -X utf8; Windows' default would be cp1252

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
        try:
            rmtree(self.tmp)
        except OSError:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
