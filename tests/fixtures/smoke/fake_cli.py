#!/usr/bin/env python3
"""Fake `claude`, `agent`, `codex` and `gh` for the smoke driver tests (#36).

The test copies this file into a temporary bin folder under each tool's name.
Every call appends {"prog", "argv", "cwd"} as one JSON line to $FAKE_RECORD.

- gh: `repo view ...` prints $FAKE_GH_SLUG; anything else (e.g. `repo create`) exits 0.
- agent create-chat: prints cursor_create_chat.txt from $FAKE_FIXTURES.
- any other call: takes the next response queued for this tool in $FAKE_QUEUE
  ({"<prog>": [{"stdout": "<fixture file>", "exit": N, "stderr": "..."}]}).
  The last queued response repeats once the queue is used up. In the fixture
  text, {SESSION_ID} becomes the value after --session-id, --resume or resume
  (a fixed id when there is none), the way the real tools echo the session.
"""
import json
import os
import sys

DEFAULT_ID = "00000000-0000-4000-8000-000000000000"


def session_id(args):
    for flag in ("--session-id", "--resume", "resume"):
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                return args[i + 1]
    return DEFAULT_ID


def main():
    prog = os.path.basename(sys.argv[0])
    args = sys.argv[1:]
    with open(os.environ["FAKE_RECORD"], "a") as f:
        f.write(json.dumps({"prog": prog, "argv": args, "cwd": os.getcwd()}) + "\n")
    fixtures = os.environ["FAKE_FIXTURES"]
    if prog == "gh":
        if args[:2] == ["repo", "view"]:
            sys.stdout.write(os.environ["FAKE_GH_SLUG"] + "\n")
        return 0
    if prog == "agent" and args[:1] == ["create-chat"]:
        with open(os.path.join(fixtures, "cursor_create_chat.txt")) as f:
            sys.stdout.write(f.read())
        return 0
    queue_path = os.environ["FAKE_QUEUE"]
    queue = []
    if os.path.exists(queue_path):
        with open(queue_path) as f:
            queue = json.load(f).get(prog, [])
    if not queue:
        sys.stderr.write("fake %s: no queued response\n" % prog)
        return 97
    state_path = queue_path + ".state"
    state = {}
    if os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)
    n = state.get(prog, 0)
    state[prog] = n + 1
    with open(state_path, "w") as f:
        json.dump(state, f)
    item = queue[min(n, len(queue) - 1)]
    with open(os.path.join(fixtures, item["stdout"])) as f:
        text = f.read()
    sys.stdout.write(text.replace("{SESSION_ID}", session_id(args)))
    sys.stderr.write(item.get("stderr", ""))
    return item.get("exit", 0)


if __name__ == "__main__":
    sys.exit(main())
