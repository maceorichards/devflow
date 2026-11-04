"""Acceptance tests for #65 (#63 user story 23): the README documents uninstalling."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def readme():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        return f.read()


def commands_block(text):
    """The fenced block under '## Commands', up to the next '## ' heading ('' if absent)."""
    m = re.search(r"^## Commands\b.*?(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return ""
    fence = re.search(r"^```[^\n]*\n(.*?)^```", m.group(0), re.M | re.S)
    return fence.group(1) if fence else ""


NOTE_LABEL = re.compile(r"^#{2,3}[ \t][^\n]*uninstall|\*\*[^*\n]*uninstall[^*\n]*\*\*", re.I | re.M)


def note_start(text):
    """Offset of the first Uninstall heading or bold label after '## Quickstart' (-1 if absent)."""
    q = re.search(r"^## Quickstart\b", text, re.M)
    if not q:
        return -1
    m = NOTE_LABEL.search(text, q.end())
    return m.start() if m else -1


def note(text):
    """The Uninstall note: from its label to the next '## ' or '### ' heading ('' if absent)."""
    start = note_start(text)
    if start < 0:
        return ""
    label_end = text.find("\n", start)
    label_end = len(text) if label_end < 0 else label_end
    end = re.compile(r"^#{2,3}[ \t]", re.M).search(text, label_end)
    return text[start:end.start() if end else len(text)]


class ReadmeUninstallTest(unittest.TestCase):
    def test_commands_block_lists_uninstall_with_dry_run(self):
        # #63 Implementation Decisions "README": an `uninstall [--dry-run]` line under Commands
        lines = commands_block(readme()).splitlines()
        self.assertTrue(
            any(re.search(r"\./sync\.sh\s+uninstall\b.*--dry-run", l) for l in lines),
            "no Commands line with ./sync.sh uninstall and --dry-run",
        )

    def test_uninstall_note_comes_after_quickstart(self):
        # #63 user story 23: explain uninstalling after the Quickstart
        text = readme()
        q = re.search(r"^## Quickstart\b", text, re.M)
        self.assertGreater(note_start(text), q.start() if q else len(text))

    def test_uninstall_note_mentions_dry_run(self):
        # #63 user story 23: the note starts with the dry run
        self.assertRegex(note(readme()), r"\./sync\.sh\s+uninstall\s+--dry-run")

    def test_uninstall_note_mentions_uninstall_without_flag(self):
        # #63 user story 23: then `./sync.sh uninstall` itself
        self.assertRegex(note(readme()), r"\./sync\.sh\s+uninstall(?![ \t]+\[?--dry-run)")

    def test_uninstall_note_says_deleting_ignore_lines_is_optional(self):
        # #63 user story 23: optionally delete the git ignore lines
        lines = note(readme()).splitlines()
        self.assertTrue(
            any(re.search(r"ignore", l, re.I) and re.search(r"optional|if you want|you can", l, re.I)
                for l in lines),
            "no line in the Uninstall note says deleting the ignore lines is optional",
        )

    def test_uninstall_note_mentions_deleting_the_clone(self):
        # #63 user story 23: delete the clone
        self.assertRegex(
            note(readme()),
            re.compile(r"\b(delete|remove)\w*\W+(?:\w+\W+){0,4}clone"
                       r"|\bclone\W+(?:\w+\W+){0,4}(delete|remove)", re.I),
        )

    def test_uninstall_note_names_clean_reinstall(self):
        # #63 Implementation Decisions "README": "uninstall, then ./sync.sh" is the clean reinstall
        paras = re.split(r"\n\s*\n", note(readme()))
        self.assertTrue(
            any(re.search(r"\buninstall", p, re.I) and "./sync.sh" in p and re.search(r"reinstall", p, re.I)
                for p in paras),
            "no paragraph in the Uninstall note names uninstall, ./sync.sh and the clean reinstall",
        )


if __name__ == "__main__":
    unittest.main()
