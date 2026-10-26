#!/usr/bin/env python3
"""devflow smoke driver: run a smoke run of devflow with headless child agent sessions.

Usage (from the devflow repo):
  python3 -I smoke/drive.py init <owner/name> <dir>
      copy the bundled fixture to <dir>, commit it on main, create a private
      GitHub repo from it with gh, and print the /setup-devflow-skills answers
  python3 -I smoke/drive.py send <label> <repo-dir> <message>
      send one message to the agent under test, in a new session for the label
      or resuming the recorded one; prints the path of the reply's text
  python3 -I smoke/drive.py step <label> <repo-dir> <goal>
      have the stand-in (read-only) write the user's reply to the label's latest
      turn, from STAND-IN.md and the goal, then send it
  python3 -I smoke/drive.py loop <label> <repo-dir> <goal> [--max N]
      repeat step until the reply holds a PR URL for the smoke repo (exit 0),
      a turn fails (exit 1) or N steps ran (exit 2; default 12)

Options for every subcommand:
  --agent NAME      the agent under test: claude, cursor or codex (default claude)
  --stand-in NAME   the stand-in's agent (default claude)
  --logs DIR        the logs folder (default smoke/logs)

The agents' command lines and output fields are in agents.json. Turn k of a
label writes <logs>/<label>-<k>.user.txt, .out, .err and .txt (the reply's
text), plus an empty .failed on failure. Session ids per label are kept in
<logs>/sessions.json. The agent under test runs with its bypass flag: use it
only in a throwaway smoke repo.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(HERE, "agents.json")
FIXTURE = os.path.join(HERE, "fixture")
STAND_IN = os.path.join(HERE, "STAND-IN.md")
LABEL_RE = re.compile(r"^[A-Za-z0-9._]+(-[A-Za-z0-9._]+)*$")

STAND_IN_PROMPT = """You are the stand-in user in a devflow smoke run. Read your brief, {brief}, and follow it.
The scenario goal: {goal}
The agent under test's latest reply is in {turn}. It reads:
<<<
{text}
>>>
Do not edit any file. Reply with only the message to send to the agent under test, nothing else."""

SETUP_ANSWERS = """Created {dir} and pushed it to the private GitHub repo {repo}.
Start the agent under test in {dir} and run /setup-devflow-skills. Its answers:
  issue tracker: GitHub
  base branch: main
  triage labels (if asked): keep the defaults
  domain docs: single-context"""


class Fail(Exception):
    """A deliberate stop: the message goes to stderr and the driver exits 1."""


def run(argv, cwd):
    """(exit code, stdout, stderr) of argv, with no shell and no stdin."""
    try:
        r = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    except OSError as e:
        return 127, "", f"{argv[0]}: {e}\n"
    return r.returncode, r.stdout, r.stderr


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


def load_agent(name):
    with open(AGENTS) as f:
        table = json.load(f)
    if name not in table:
        raise Fail(f"unknown agent {name!r}; agents.json has {', '.join(sorted(table))}")
    return table[name]


def argv_for(agent, key, msg, sid=None):
    """Fill the agent's argv template: {msg} and {id} are one element each,
    {bypass} and {read_only} splice in the agent's flags."""
    out = []
    for part in agent[key]:
        if part in ("{bypass}", "{read_only}"):
            out += agent[part[1:-1]]
        else:
            out.append({"{msg}": msg, "{id}": sid}.get(part, part))
    return out


# -- output parsing: (ok, text, session id) -----------------------------------
def parse(agent, code, out):
    spec = agent["output"]
    if spec["format"] == "jsonl":
        return parse_jsonl(spec, code, out)
    return parse_json(spec, code, out)


def parse_json(spec, code, out):
    obj = None
    for candidate in (out, (out.strip().splitlines() or [""])[-1]):
        try:
            obj = json.loads(candidate)
            break
        except ValueError:
            continue
    if not isinstance(obj, dict):
        return False, "", None
    text = obj.get(spec["text"])
    ok = (code == 0 and obj.get(spec["is_error"]) is not True
          and obj.get(spec["subtype"]) in (None, spec["ok_subtype"]))
    return ok, text if isinstance(text, str) else "", obj.get(spec["session_id"])


def parse_jsonl(spec, code, out):
    sid, text, done, failed = None, "", False, False
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        kind = ev.get("type")
        if kind == spec["session_id"]["event"] and sid is None:
            sid = ev.get(spec["session_id"]["field"])
        elif kind == spec["text"]["event"]:
            item = ev.get("item") or {}
            if item.get("type") == spec["text"]["item_type"]:
                text = item.get(spec["text"]["field"]) or ""
        done = done or kind == spec["done"]
        failed = failed or kind in spec["failed"]
    return code == 0 and done and not failed, text, sid


# -- logs ---------------------------------------------------------------------
def turns(logs, label):
    """The label's logged turn numbers, ascending."""
    pat = re.compile(re.escape(label) + r"-(\d+)\.user\.txt$")
    return sorted(int(m.group(1)) for m in map(pat.match, os.listdir(logs)) if m)


def latest(logs, label):
    """Path prefix <logs>/<label>-<k> of the label's latest turn."""
    ks = turns(logs, label)
    if not ks:
        raise Fail(f"no turn yet for {label}: run send first")
    return os.path.join(logs, f"{label}-{ks[-1]}")


def load_sessions(logs):
    path = os.path.join(logs, "sessions.json")
    return json.loads(read(path)) if os.path.exists(path) else {}


def save_sessions(logs, sessions):
    path = os.path.join(logs, "sessions.json")
    write(path + ".tmp", json.dumps(sessions, indent=2) + "\n")
    os.replace(path + ".tmp", path)


# -- turns --------------------------------------------------------------------
def send(logs, name, label, repo, msg):
    """Run one turn of the agent under test; (ok, path of the reply's .txt)."""
    agent = load_agent(name)
    sessions = load_sessions(logs)
    rec = sessions.get(label)
    if rec and rec["agent"] != name:
        raise Fail(f"{label} is a {rec['agent']} session: use --agent {rec['agent']} or a new label")
    base = os.path.join(logs, f"{label}-{(turns(logs, label) or [0])[-1] + 1}")
    write(base + ".user.txt", msg)
    sid = rec["session_id"] if rec else None
    ok, text, out, err = False, "", "", ""
    if sid:
        argv = argv_for(agent, "resume", msg, sid)
    elif agent["session"] == "caller":
        sid = str(uuid.uuid4())
        argv = argv_for(agent, "new", msg, sid)
    elif agent["session"] == "create":
        code, out, err = run(agent["create"], repo)
        sid = out.strip() if code == 0 else None
        argv = argv_for(agent, "new", msg, sid) if sid else None
    else:
        argv = argv_for(agent, "new", msg)
    if argv:
        code, out, err = run(argv, repo)
        ok, text, out_sid = parse(agent, code, out)
        if not rec:
            # caller-chosen ids count once the tool reports a session; codex's comes from the output
            keep = {"caller": sid if out_sid else None, "create": sid, "output": out_sid}[agent["session"]]
            if keep:
                sessions[label] = {"agent": name, "session_id": keep}
                save_sessions(logs, sessions)
    write(base + ".out", out)
    write(base + ".err", err)
    write(base + ".txt", text)
    if not ok:
        write(base + ".failed", "")
    return ok, base + ".txt"


def stand_in(logs, name, label, goal):
    """Run the stand-in (read-only, new session) on the latest turn; (ok, reply)."""
    base = latest(logs, label)
    prompt = STAND_IN_PROMPT.format(brief=STAND_IN, goal=goal, turn=base + ".txt",
                                    text=read(base + ".txt").strip())
    agent = load_agent(name)
    code, out, err = run(argv_for(agent, "stand_in", prompt), HERE)
    ok, text, _ = parse(agent, code, out)
    write(base + ".standin.out", out)
    write(base + ".standin.err", err)
    write(base + ".standin.txt", text)
    return ok and bool(text.strip()), text.strip()


# -- subcommands --------------------------------------------------------------
def cmd_send(a):
    ok, txt = send(a.logs, a.agent, a.label, a.repo_dir, a.message)
    print(txt)
    return 0 if ok else 1


def cmd_step(a):
    ok, reply = stand_in(a.logs, a.stand_in, a.label, a.goal)
    if not ok:
        print(f"stand-in turn failed: see {latest(a.logs, a.label)}.standin.*", file=sys.stderr)
        return 1
    return cmd_send(argparse.Namespace(**dict(vars(a), message=reply)))


def cmd_loop(a):
    code, out, err = run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                         a.repo_dir)
    slug = out.strip()
    if code != 0 or not slug:
        raise Fail(f"gh repo view failed in {a.repo_dir}:\n{err}")
    pr = re.compile(r"https://github\.com/" + re.escape(slug) + r"/pull/\d+", re.IGNORECASE)
    for n in range(a.max + 1):
        base = latest(a.logs, a.label)
        m = pr.search(read(base + ".txt"))
        if m:
            print(f"STOP {a.label}: pr {m.group(0)}")
            return 0
        if os.path.exists(base + ".failed"):
            print(f"STOP {a.label}: error {base}.txt")
            return 1
        if n == a.max:
            break
        ok, reply = stand_in(a.logs, a.stand_in, a.label, a.goal)
        if not ok:
            print(f"STOP {a.label}: step failed")
            return 1
        print(send(a.logs, a.agent, a.label, a.repo_dir, reply)[1])
    print(f"STOP {a.label}: max steps")
    return 2


def cmd_init(a):
    target = os.path.abspath(a.dir)
    if os.path.lexists(target):
        raise Fail(f"{target} already exists")
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    for argv in (["git", "init", "-q", "-b", "main"],
                 ["git", "add", "-A"],
                 ["git", "commit", "-q", "-m", "Smoke fixture"],
                 ["gh", "repo", "create", a.repo, "--private", "--source", target, "--push"]):
        code, out, err = run(argv, target)
        if code != 0:
            raise Fail(f"{' '.join(argv)} failed:\n{out}{err}")
    print(SETUP_ANSWERS.format(dir=target, repo=a.repo))
    return 0


def parse_args(argv):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--agent", default="claude", help="the agent under test")
    common.add_argument("--stand-in", default="claude", help="the stand-in's agent")
    common.add_argument("--logs", default=os.path.join(HERE, "logs"), help="the logs folder")
    p = argparse.ArgumentParser(prog="drive.py", description="devflow smoke driver")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", parents=[common], help="create the smoke repo from the fixture")
    s.add_argument("repo", metavar="owner/name")
    s.add_argument("dir")
    s.set_defaults(func=cmd_init)
    for name, last, func in (("send", "message", cmd_send), ("step", "goal", cmd_step),
                             ("loop", "goal", cmd_loop)):
        s = sub.add_parser(name, parents=[common])
        s.add_argument("label")
        s.add_argument("repo_dir", metavar="repo-dir")
        s.add_argument(last)
        s.set_defaults(func=func)
    s.add_argument("--max", type=int, default=12, help="the step limit (default 12)")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if a.cmd != "init":
            if not LABEL_RE.match(a.label):
                raise Fail(f"bad label {a.label!r}: use letters, digits, '.', '_' and '-'")
            a.repo_dir = os.path.abspath(a.repo_dir)
            a.logs = os.path.abspath(a.logs)
            os.makedirs(a.logs, exist_ok=True)
        return a.func(a)
    except Fail as e:
        print(f"drive.py: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
