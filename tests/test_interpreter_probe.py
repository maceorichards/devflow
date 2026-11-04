"""Acceptance tests for #55: the interpreter probe in sync.sh (black-box, via the sync CLI).

Expected behaviour (#52, user stories 1-6; ticket #55): sync.sh tries `python3`, then `python`,
then `py -3`, and runs the first that reports Python 3.9+ with `-I -X utf8`, then lib/sync.py,
then the user's arguments. If none qualifies it says devflow needs Python 3.9+, names every
candidate tried, and exits 1.

Fake interpreters on PATH are the system boundary here. All three names are shadowed in every
test, since a real /usr/bin/python3 (and sometimes python) exists on Linux and macOS.
Each fake call is recorded as its own file in a log dir (NUL-separated: name, kind, argv), so
argv containing newlines (the probe's `-c` code) can't break the record format.
"""
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest

from tests.harness import SyncSandbox

REAL_PYTHON = sys.executable
STORE_MESSAGE = ("Python was not found; run without arguments to install from the "
                 "Microsoft Store, or disable this shortcut from Settings > Apps > "
                 "Advanced app settings > App execution aliases.")

_LOG = r'''_log() {
  f=$(mktemp "$LOGDIR/call.XXXXXX")
  printf '%s\0' "$@" > "$f"
}
'''

# Store-shim-like: complains and fails for any invocation. 9009 is cmd.exe's "not found"
# status (#48); POSIX truncates it to 49, which is non-zero and, importantly, not 1.
_BROKEN = r'''#!/bin/sh
LOGDIR='{logdir}'
{log}_log '{name}' broken "$@"
echo "{msg}" >&2
exit 9009
'''

# Working: log, then exec the real interpreter. The py flavour drops a leading -3.
_WORKING = r'''#!/bin/sh
LOGDIR='{logdir}'
{log}_log '{name}' working "$@"
{drop3}exec '{real}' "$@"
'''
_DROP3 = 'if [ "${1:-}" = "-3" ]; then shift; fi\n'

# Old (3.8): `-c <code>` runs <code> in the real interpreter with sys.version_info replaced by a
# 5-field namedtuple (3, 8, 18, 'final', 0); --version/-V prints 3.8.18; anything else is
# logged and exits 0 without running anything.
_OLD_WRAPPER = (
    'import collections, sys\n'
    'VI = collections.namedtuple("version_info", "major minor micro releaselevel serial")\n'
    'sys.version_info = VI(3, 8, 18, "final", 0)\n'
    'code = sys.argv[1]\n'
    'sys.argv = ["-c"]\n'
    'exec(compile(code, "<string>", "exec"), {"__name__": "__main__"})\n'
)  # double quotes only: it is embedded in a single-quoted shell string
_OLD = r'''#!/bin/sh
LOGDIR='{logdir}'
{log}_log '{name}' old "$@"
{drop3}for a in "$@"; do
  case "$a" in --version|-V) echo "Python 3.8.18"; exit 0;; esac
done
prev=
for a in "$@"; do
  if [ "$prev" = "-c" ]; then exec '{real}' -c '{wrapper}' "$a"; fi
  prev=$a
done
exit 0
'''

NAMES = {"python3": "python3", "python": "python", "py": "py"}


class InterpreterProbeTest(unittest.TestCase):
    def setUp(self):
        self.sb = SyncSandbox()
        self.addCleanup(self.sb.close)
        self.bin = tempfile.mkdtemp(prefix="devflow-fakepy-")
        self.addCleanup(shutil.rmtree, self.bin, True)
        self.logdir = os.path.join(self.bin, "log")
        os.makedirs(self.logdir)

    # --- fakes ---------------------------------------------------------------------------

    def _fake(self, name, kind):
        drop3 = _DROP3 if name == "py" else ""
        fmt = dict(logdir=self.logdir, log=_LOG, name=name, real=REAL_PYTHON, drop3=drop3)
        if kind == "broken":
            text = _BROKEN.format(msg=STORE_MESSAGE, **fmt)
        elif kind == "working":
            text = _WORKING.format(**fmt)
        elif kind == "old":
            text = _OLD.format(wrapper=_OLD_WRAPPER, **fmt)
        else:
            raise ValueError(kind)
        path = os.path.join(self.bin, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _run(self, python3, python, py):
        self._fake("python3", python3)
        self._fake("python", python)
        self._fake("py", py)
        path = self.bin + os.pathsep + os.environ.get("PATH", "")
        return self.sb.run("--dry-run", env={"PATH": path})

    def _calls(self):
        calls = []
        for n in sorted(os.listdir(self.logdir)):
            with open(os.path.join(self.logdir, n), "rb") as f:
                fields = f.read().decode("utf-8").split("\0")[:-1]
            calls.append((fields[0], fields[1], fields[2:]))
        return calls

    def _sync_calls(self):
        """(name, argv) of every fake call whose argv holds the sync script lib/sync.py."""
        return [(name, argv) for name, _kind, argv in self._calls()
                if any(a.replace("\\", "/").endswith("lib/sync.py") for a in argv)]

    def _ran_by(self):
        return [name for name, _argv in self._sync_calls()]

    def _missing_from_message(self, stderr):
        # Substring/word checks, since wording may vary (#52, user stories 4 and 5).
        needles = {"3.9": r"3\.9", "python3": r"\bpython3\b", "python": r"\bpython\b",
                   "py -3": r"\bpy -3\b"}
        return [k for k, rx in needles.items() if not re.search(rx, stderr)]

    # --- order and fall-through (#52, user stories 1, 3, 6; ticket #55 criterion 1) -------

    def test_working_python3_runs_the_sync(self):
        # characterization: today's behaviour (#52, user story 6)
        r = self._run(python3="working", python="broken", py="broken")
        self.assertEqual((r.returncode, self._ran_by()), (0, ["python3"]), r.stderr)

    def test_store_shim_python3_falls_through_to_python(self):
        # #52, user story 1 (#48)
        r = self._run(python3="broken", python="working", py="broken")
        self.assertEqual((r.returncode, self._ran_by()), (0, ["python"]), r.stderr)

    def test_launcher_only_runs_the_sync_with_py(self):
        # #52, user story 3
        r = self._run(python3="broken", python="broken", py="working")
        self.assertEqual((r.returncode, self._ran_by()), (0, ["py"]), r.stderr)

    def test_launcher_is_invoked_as_py_dash_3(self):
        # #52, user story 3: the candidate is `py -3`, so its argv begins with -3
        self._run(python3="broken", python="broken", py="working")
        firsts = [argv[0] if argv else None for _n, argv in self._sync_calls()]
        self.assertEqual(firsts, ["-3"])

    # --- flags (#52 Implementation Decisions: run with -I -X utf8, script, user args) -----

    def test_sync_runs_isolated_and_utf8_with_user_args_after_script(self):
        self._run(python3="working", python="broken", py="broken")
        calls = self._sync_calls()
        self.assertEqual(len(calls), 1, calls)
        argv = calls[0][1]
        i = next(k for k, a in enumerate(argv) if a.replace("\\", "/").endswith("lib/sync.py"))
        before, after = argv[:i], argv[i + 1:]
        utf8 = any(before[k] == "-X" and before[k + 1] == "utf8" for k in range(len(before) - 1))
        self.assertEqual({"-I before script": "-I" in before,
                          "-X utf8 before script": utf8,
                          "args after script": after},
                         {"-I before script": True,
                          "-X utf8 before script": True,
                          "args after script": ["--dry-run"]})

    # --- version floor (#52, user story 4; ticket #55 criterion 1) ------------------------

    def test_old_python3_is_skipped_for_working_python(self):
        r = self._run(python3="old", python="working", py="broken")
        self.assertEqual((r.returncode, self._ran_by()), (0, ["python"]), r.stderr)

    # --- no qualifying interpreter (#52, user stories 4 and 5; ticket #55 criterion 2) ----

    def test_only_old_interpreters_exits_1(self):
        r = self._run(python3="old", python="old", py="broken")
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_only_old_interpreters_message_names_floor_and_every_candidate(self):
        r = self._run(python3="old", python="old", py="broken")
        self.assertEqual(self._missing_from_message(r.stderr), [], r.stderr)

    def test_only_old_interpreters_never_run_the_sync(self):
        self._run(python3="old", python="old", py="broken")
        self.assertEqual(self._ran_by(), [])

    def test_no_usable_interpreter_exits_1(self):
        r = self._run(python3="broken", python="broken", py="broken")
        self.assertEqual(r.returncode, 1, r.stderr)

    def test_no_usable_interpreter_message_names_floor_and_every_candidate(self):
        r = self._run(python3="broken", python="broken", py="broken")
        self.assertEqual(self._missing_from_message(r.stderr), [], r.stderr)


if __name__ == "__main__":
    unittest.main()
