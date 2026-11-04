"""Acceptance tests for #53 (part of #52): every text read and write in the sync library and
the smoke driver names its encoding.

On Windows the locale encoding is cp1252, so text I/O without an explicit encoding reads,
writes or decodes non-ASCII skill text wrongly (#49; #52 user stories 7 and 20). UTF-8 is
already the default on Linux and macOS, so the defect can't be observed there by running the
code. The guard below is a static check by design (#52 user story 21): it parses each source
file's AST and lists every text-mode call that doesn't pass encoding="utf-8".
"""
import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_UTF8 = {"utf-8", "utf8"}


def _keyword(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw
    return None


def _mode_is_text(call):
    """The mode is the 2nd positional arg or mode=. Absent, or a str constant without "b",
    is text. A mode that isn't a str constant can't be proven binary, so it counts as text."""
    mode = call.args[1] if len(call.args) > 1 else None
    kw = _keyword(call, "mode")
    if kw is not None:
        mode = kw.value
    if mode is None:
        return True
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return "b" not in mode.value
    return True


def _is_text_flag(kw):
    # text=False / text=None is bytes mode; anything else (True, or a value that isn't a
    # constant) may be text, so it must name an encoding.
    if kw is None:
        return False
    return not (isinstance(kw.value, ast.Constant) and kw.value.value in (False, None))


def _call_kind(call):
    """'open', 'fdopen' or 'subprocess' for the calls the guard covers, else None."""
    f = call.func
    if isinstance(f, ast.Name) and f.id == "open":
        return "open"
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        if f.value.id == "os" and f.attr == "fdopen":
            return "fdopen"
        if f.value.id == "subprocess":
            return "subprocess"
    return None


def _is_text_call(call, kind):
    if kind in ("open", "fdopen"):
        return _mode_is_text(call)
    return (_is_text_flag(_keyword(call, "text"))
            or _is_text_flag(_keyword(call, "universal_newlines")))


def _encoding_ok(call):
    """True when encoding= is present and isn't a str constant other than utf-8/utf8.
    encoding=None means the locale encoding, so it counts as missing."""
    kw = _keyword(call, "encoding")
    if kw is None:
        return False
    v = kw.value
    if isinstance(v, ast.Constant):
        return isinstance(v.value, str) and v.value.lower() in _UTF8
    return True


def find_violations(source, filename="<snippet>"):
    """List of 'file:line: call text' for each text-mode open()/os.fdopen()/subprocess call
    without encoding="utf-8"."""
    tree = ast.parse(source, filename)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _call_kind(node)
        if kind is None:
            continue
        has_enc = _keyword(node, "encoding") is not None
        if not has_enc and not _is_text_call(node, kind):
            continue
        if _encoding_ok(node):
            continue
        text = ast.get_source_segment(source, node) or ast.dump(node)
        out.append((node.lineno, f"{filename}:{node.lineno}: {' '.join(text.split())}"))
    return [msg for _, msg in sorted(out)]


def violations_in(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return find_violations(f.read(), rel)


class SourceEncodingTest(unittest.TestCase):
    # #52 Implementation Decisions, encoding policy; ticket #53 criteria 1 and 5;
    # #52 user story 21.
    def assertNoViolations(self, rel):
        found = violations_in(rel)
        self.assertEqual(found, [], "text I/O without encoding=\"utf-8\":\n" + "\n".join(found))

    def test_sync_library_names_utf8_for_every_text_io_call(self):
        # #52 user stories 7 and 8: the sync reads, writes and decodes as UTF-8
        self.assertNoViolations("lib/sync.py")

    def test_smoke_driver_names_utf8_for_every_text_io_call(self):
        # #52 user story 20: the smoke driver decodes agent output and its files as UTF-8
        self.assertNoViolations("smoke/drive.py")


class GuardSelfTest(unittest.TestCase):
    """Tests of the guard itself (test code, so these pass as soon as the guard exists).
    Cases come from the violation rules for #53."""

    def assertFlagged(self, src):
        self.assertEqual(len(find_violations(src)), 1, src)

    def assertNotFlagged(self, src):
        self.assertEqual(find_violations(src), [], src)

    def test_bare_text_open_is_flagged(self):
        self.assertFlagged("open(p)\n")

    def test_binary_open_is_not_flagged(self):
        self.assertNotFlagged('open(p, "rb")\n')

    def test_text_open_with_utf8_is_not_flagged(self):
        self.assertNotFlagged('open(p, "w", encoding="utf-8")\n')

    def test_text_fdopen_without_encoding_is_flagged(self):
        self.assertFlagged('os.fdopen(fd, "w", newline=x)\n')

    def test_text_subprocess_without_encoding_is_flagged(self):
        self.assertFlagged("subprocess.run(a, text=True)\n")

    def test_text_subprocess_with_utf8_is_not_flagged(self):
        self.assertNotFlagged('subprocess.run(a, text=True, encoding="utf-8")\n')

    def test_bytes_subprocess_is_not_flagged(self):
        self.assertNotFlagged("subprocess.run(a)\n")

    def test_open_with_non_utf8_encoding_is_flagged(self):
        self.assertFlagged('open(p, encoding="latin-1")\n')


if __name__ == "__main__":
    unittest.main()
