"""Acceptance tests for #54 (#52 user stories 11-15, 17): line endings independent of the
user's git config. Black-box, through ./sync.sh in a SyncSandbox. `core.autocrlf=true` converts
LF to CRLF on checkout on every OS, so the Windows defect (#50) reproduces on Linux and macOS."""
import glob
import os
import re
import unittest

from tests.harness import REAL_ROOT, SyncSandbox

CLAUDE_SKILLS = "~/.claude/skills"
# The CI fresh-install job's "no change" check: every status that changes something starts
# its line with one of these words.
CHANGE_LINE = re.compile(r"^\s*(installed|updated|removed|added|would|FAIL|WARN|SKIP)(\s|$)")


def _to_crlf(path):
    with open(path, "rb") as f:
        data = f.read()
    data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    with open(path, "wb") as f:
        f.write(data)


def _patch_paths(sb):
    return sorted(glob.glob(os.path.join(sb.repo, "patches", "*.patch")))


def _tracked_files(sb, clone):
    out = sb.git("ls-files", "-z", cwd=clone).stdout
    paths = [os.path.join(clone, p) for p in out.split("\0") if p]
    return [p for p in paths if os.path.isfile(p) and not os.path.islink(p)]


def _files_with_cr(sb, clone):
    """Tracked text files containing a CR. Binary files (a NUL byte, git's own heuristic) are
    skipped: line endings don't apply to them, and e.g. every PNG's signature holds a CR."""
    bad = []
    for p in _tracked_files(sb, clone):
        with open(p, "rb") as f:
            data = f.read()
        if b"\r" in data and b"\0" not in data:
            bad.append(os.path.relpath(p, clone))
    return bad


def _tree(root):
    """{relative path: bytes} of every file under root ({} if root doesn't exist)."""
    out = {}
    for dp, _, files in os.walk(root):
        for fn in files:
            p = os.path.join(dp, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


def _local_autocrlf(sb, clone):
    r = sb.git("config", "--local", "--get", "core.autocrlf", cwd=clone, check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def _change_lines(stdout):
    return [l for l in stdout.splitlines() if CHANGE_LINE.match(l)]


class _Base(unittest.TestCase):
    def sandbox(self, **kw):
        sb = SyncSandbox(**kw)
        self.addCleanup(sb.close)
        return sb

    def assert_every_skill_installed(self, sb, r):
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertEqual([l for l in r.stdout.splitlines() if l.lstrip().startswith("FAIL")], [], out)
        self.assertEqual(sb.managed_skills(CLAUDE_SKILLS), sb.manifest_skill_names(), out)

    def assert_no_change(self, r):
        self.assertEqual(_change_lines(r.stdout), [], r.stdout + r.stderr)


class CrlfPatchesTest(_Base):
    """#52 user stories 11 and 14: a clone whose patches/*.patch are CRLF still syncs."""

    def setUp(self):
        self.sb = self.sandbox()
        for p in _patch_paths(self.sb):
            _to_crlf(p)

    def test_crlf_patches_install_every_skill(self):
        self.assert_every_skill_installed(self.sb, self.sb.run())

    def test_crlf_patches_resync_reports_no_change(self):
        self.sb.run()
        self.assert_no_change(self.sb.run())


class CrlfVendorClonesTest(_Base):
    """#52 user story 12: vendor clones checked out under core.autocrlf=true are repaired once."""

    def setUp(self):
        self.sb = self.sandbox(own_vendors=True)
        self.sb.set_global_git_config("core.autocrlf", "true")
        self.sb.clone_vendors()
        # Precondition: without a CRLF file in mattpocock-skills (no upstream eol rule) the
        # cases below prove nothing.
        matt = self.sb.vendor_dirs()["matt"]
        self.assertNotEqual(_files_with_cr(self.sb, matt), [],
                            "pre-cloned mattpocock-skills has no CRLF file under core.autocrlf=true")

    def test_crlf_vendor_clones_install_every_skill(self):
        # characterization: passes today, because git apply honours the effective
        # core.autocrlf=true and normalises the CRLF vendor files before matching the patch.
        self.assert_every_skill_installed(self.sb, self.sb.run())

    def test_crlf_vendor_clones_are_lf_after_sync(self):
        self.sb.run()
        bad = {src: _files_with_cr(self.sb, d) for src, d in self.sb.vendor_dirs().items()}
        self.assertEqual({src: f for src, f in bad.items() if f}, {})

    def test_crlf_vendor_clones_get_local_autocrlf_false(self):
        self.sb.run()
        got = {src: _local_autocrlf(self.sb, d) for src, d in self.sb.vendor_dirs().items()}
        self.assertEqual(got, {src: "false" for src in got})

    def test_crlf_vendor_clones_installed_skills_are_lf(self):
        # #52 user story 9: installed skill files are LF, byte-for-byte as on macOS.
        sb = self.sb
        r = sb.run()
        root = sb.home_path(CLAUDE_SKILLS)
        bad = [os.path.join(n, p) for n in sorted(sb.managed_skills(CLAUDE_SKILLS))
               for p, data in _tree(os.path.join(root, n)).items() if b"\r" in data]
        self.assertEqual(bad, [], r.stdout + r.stderr)

    def test_crlf_vendor_clones_resync_reports_no_change(self):
        # characterization: passes today (nothing changes the clones between the two syncs).
        self.sb.run()
        self.assert_no_change(self.sb.run())


class MissingVendorClonesTest(_Base):
    """#52 user story 11: a vendor clone the sync creates is LF even under global autocrlf=true."""

    def setUp(self):
        self.sb = self.sandbox(own_vendors=True)
        self.sb.set_global_git_config("core.autocrlf", "true")

    def test_new_clones_install_every_skill(self):
        # characterization: passes today for the same reason as the pre-cloned case.
        self.assert_every_skill_installed(self.sb, self.sb.run())

    def test_new_clones_are_lf(self):
        self.sb.run()
        bad = {src: _files_with_cr(self.sb, d) for src, d in self.sb.vendor_dirs().items()}
        self.assertEqual({src: f for src, f in bad.items() if f}, {})

    def test_new_clones_record_local_autocrlf_false(self):
        self.sb.run()
        got = {src: _local_autocrlf(self.sb, d) for src, d in self.sb.vendor_dirs().items()}
        self.assertEqual(got, {src: "false" for src in got})


class AutocrlfNotTrueTest(_Base):
    """#52 user story 13: when the effective core.autocrlf isn't true, the repair never runs.
    Characterization: today's sync never touches an existing clone at its locked commit."""

    def pre_cloned(self, global_autocrlf):
        sb = self.sandbox(own_vendors=True)
        if global_autocrlf is not None:
            sb.set_global_git_config("core.autocrlf", global_autocrlf)
        sb.clone_vendors()
        return sb

    def mtimes(self, sb):
        return {p: os.stat(p).st_mtime_ns
                for d in sb.vendor_dirs().values() for p in _tracked_files(sb, d)}

    def assert_no_local_key(self, global_autocrlf):
        sb = self.pre_cloned(global_autocrlf)
        r = sb.run()
        got = {src: _local_autocrlf(sb, d) for src, d in sb.vendor_dirs().items()}
        self.assertEqual(got, {src: None for src in got}, r.stdout + r.stderr)

    def assert_files_untouched(self, global_autocrlf):
        sb = self.pre_cloned(global_autocrlf)
        before = self.mtimes(sb)
        r = sb.run()
        self.assertEqual(self.mtimes(sb), before, r.stdout + r.stderr)

    def test_autocrlf_input_adds_no_local_key(self):
        self.assert_no_local_key("input")

    def test_autocrlf_input_leaves_tracked_files_untouched(self):
        self.assert_files_untouched("input")

    def test_autocrlf_unset_adds_no_local_key(self):
        self.assert_no_local_key(None)

    def test_autocrlf_unset_leaves_tracked_files_untouched(self):
        self.assert_files_untouched(None)


class EditCrlfPatchTest(_Base):
    """#52 user story 15: `sync.sh edit` applies a CRLF patch the same way the build does."""

    def test_edit_applies_crlf_patch(self):
        sb = self.sandbox()
        _to_crlf(os.path.join(sb.repo, "patches", "grilling.patch"))
        r = sb.run("edit", "grilling")
        work = os.path.join(sb.repo, ".patch-work", "grilling")
        # A missing a/ or b/ reads as an empty tree, so a crashed edit fails here too.
        self.assertNotEqual(_tree(os.path.join(work, "a")), _tree(os.path.join(work, "b")),
                            "b/ equals a/: the patch was not applied\n" + r.stdout + r.stderr)


class FailingPatchTest(_Base):
    """#54 criterion 5: a patch that genuinely doesn't apply is still reported, naming the file.
    Characterization: today's sync already prints this FAIL line and exits non-zero."""

    PATCH = "patches/grilling.patch"

    def setUp(self):
        self.sb = self.sandbox()
        path = os.path.join(self.sb.repo, self.PATCH)
        with open(path, encoding="utf-8", newline="") as f:
            lines = f.read().split("\n")
        in_hunk = False
        for i, line in enumerate(lines):
            if line.startswith("@@"):
                in_hunk = True
            elif in_hunk and line.startswith(" ") and line.strip():
                lines[i] = " devflow-test: this context line matches nothing upstream"
                break
        else:
            self.fail(f"no context line to corrupt in {self.PATCH}")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines))
        self.r = self.sb.run()

    def test_unappliable_patch_fail_line_names_patch_file(self):
        fails = [l for l in self.r.stdout.splitlines()
                 if l.lstrip().startswith("FAIL") and self.PATCH in l]
        self.assertNotEqual(fails, [], self.r.stdout + self.r.stderr)

    def test_unappliable_patch_exits_non_zero(self):
        self.assertNotEqual(self.r.returncode, 0, self.r.stdout + self.r.stderr)


class GitattributesTest(unittest.TestCase):
    """#54 criterion 1 (#52 user story 17): the repo declares LF for its text files."""

    def test_repo_gitattributes_declares_lf(self):
        path = os.path.join(REAL_ROOT, ".gitattributes")
        lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = [l.strip() for l in f.read().splitlines()]
        self.assertIn("* text=auto eol=lf", lines)


if __name__ == "__main__":
    unittest.main()
