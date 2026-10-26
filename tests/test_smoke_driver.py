"""Acceptance tests for #36 (#34 part D): the smoke driver `smoke/drive.py` (black-box).

The seam: `python3 -I smoke/drive.py ...` run as a subprocess, with fake `claude`,
`agent`, `codex` and `gh` executables first on PATH (tests/fixtures/smoke/fake_cli.py).
The fakes record their argv and cwd and print recorded sample outputs. git is real.
No live agent, no network.

Options are passed after the subcommand's positionals (`send <label> <repo> <msg>
--agent X --logs D`), the form `loop <label> <repo-dir> <goal> [--max N]` shows.

Text files the driver writes (.user.txt, .txt, .standin.txt) are compared after
dropping trailing newlines: #36 fixes their content, not whether a final newline
is written. Raw stdout/stderr (.out, .err) are compared exactly.

A crashing driver also exits 1, so where a test pins "exits 1" it checks that the
exit is deliberate: code 1 and no Python traceback on stderr.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SMOKE = os.path.join(ROOT, "smoke")
DRIVE = os.path.join(SMOKE, "drive.py")
AGENTS_JSON = os.path.join(SMOKE, "agents.json")
FIXTURE_PKG = os.path.join(SMOKE, "fixture")
STAND_IN_MD = os.path.join(SMOKE, "STAND-IN.md")
FIXTURES = os.path.join(HERE, "fixtures", "smoke")
FAKE = os.path.join(FIXTURES, "fake_cli.py")

SLUG = "smoke-owner/smoke-repo"
LABEL = "smoke"
GOAL = "Approve the spec as written and keep going until a PR is open."

# Extracted final texts of the recorded samples in tests/fixtures/smoke/.
CLAUDE_TEXT = "Claude says: spec drafted."
STANDIN_TEXT = "Yes, go with option A."
CURSOR_TEXT = "Cursor says: done."
CODEX_TEXT = "Codex says: tests pass."
CURSOR_CHAT_ID = "c0ffee00-1234-4abc-8def-0123456789ab"
CODEX_THREAD_ID = "0199a213-81c0-7800-8aa1-bbab2a035a53"
PR_URL = "https://github.com/smoke-owner/smoke-repo/pull/7"

# Agent name -> executable name (#36 agent command table).
PROG = {"claude": "claude", "cursor": "agent", "codex": "codex"}


def _strip_nl(text):
    return text.rstrip("\n")


class DriverCase(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="devflow-smoke-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        for name in ("claude", "agent", "codex", "gh"):
            dest = os.path.join(self.bin, name)
            shutil.copy(FAKE, dest)
            os.chmod(dest, 0o755)
        self.logs = os.path.join(self.tmp, "logs")  # not created: the driver creates it
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.cwd = os.path.join(self.tmp, "elsewhere")
        os.makedirs(self.cwd)
        self.record = os.path.join(self.tmp, "calls.jsonl")
        self.queue_path = os.path.join(self.tmp, "queue.json")
        self.queue = {}
        self.gitconfig = os.path.join(self.tmp, "gitconfig")
        open(self.gitconfig, "w").close()

    # -- fakes -------------------------------------------------------------
    def enqueue(self, prog, stdout, exit=0, stderr=""):
        self.queue.setdefault(prog, []).append({"stdout": stdout, "exit": exit, "stderr": stderr})
        with open(self.queue_path, "w") as f:
            json.dump(self.queue, f)

    def env(self):
        env = dict(os.environ)
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        env.update({
            "FAKE_RECORD": self.record,
            "FAKE_QUEUE": self.queue_path,
            "FAKE_FIXTURES": FIXTURES,
            "FAKE_GH_SLUG": SLUG,
            "GIT_CONFIG_GLOBAL": self.gitconfig,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Smoke Test",
            "GIT_AUTHOR_EMAIL": "smoke@example.invalid",
            "GIT_COMMITTER_NAME": "Smoke Test",
            "GIT_COMMITTER_EMAIL": "smoke@example.invalid",
        })
        return env

    def calls(self, prog=None):
        if not os.path.exists(self.record):
            return []
        with open(self.record) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        return [r for r in rows if prog is None or r["prog"] == prog]

    def argvs(self, prog):
        return [c["argv"] for c in self.calls(prog)]

    # -- driver ------------------------------------------------------------
    def drive(self, *args, logs=True):
        cmd = [sys.executable, "-I", DRIVE] + list(args)
        if logs:
            cmd += ["--logs", self.logs]
        return subprocess.run(cmd, cwd=self.cwd, env=self.env(), capture_output=True,
                              text=True, timeout=300)

    def send(self, message, *opts):
        return self.drive("send", LABEL, self.repo, message, *opts)

    def send_ok(self, message, *opts):
        r = self.send(message, *opts)
        self.assertEqual(r.returncode, 0, "precondition: send failed\n" + r.stdout + r.stderr)
        return r

    def step(self, *opts):
        return self.drive("step", LABEL, self.repo, GOAL, *opts)

    def step_ok(self, *opts):
        r = self.step(*opts)
        self.assertEqual(r.returncode, 0, "precondition: step failed\n" + r.stdout + r.stderr)
        return r

    def loop(self, *opts):
        return self.drive("loop", LABEL, self.repo, GOAL, *opts)

    def assertDeliberateExit(self, r, code, msg="exit"):
        self.assertEqual((r.returncode, "Traceback" in r.stderr), (code, False),
                         "%s: expected a deliberate exit %d\n%s%s" % (msg, code, r.stdout, r.stderr))

    # -- logs --------------------------------------------------------------
    def log(self, name):
        return os.path.join(self.logs, name)

    def read(self, path):
        self.assertTrue(os.path.exists(path), "missing " + path)
        with open(path) as f:
            return f.read()

    def sessions(self):
        return json.loads(self.read(self.log("sessions.json")))


class AgentTableTest(unittest.TestCase):
    def _table(self):
        self.assertTrue(os.path.exists(AGENTS_JSON), "missing smoke/agents.json")
        with open(AGENTS_JSON) as f:
            return json.load(f)

    def test_agents_json_has_exactly_claude_cursor_codex(self):
        # #36 / #34 user story 46: claude, cursor and codex entries, gemini omitted
        self.assertEqual(set(self._table()), {"claude", "cursor", "codex"})

    def test_agents_json_verified_only_for_claude_and_cursor(self):
        # #36 / #34 user story 46: codex is unverified until smoke-run
        table = self._table()
        self.assertEqual({k: v.get("verified") for k, v in table.items()},
                         {"claude": True, "cursor": True, "codex": False})


class ClaudeSendTest(DriverCase):
    def setUp(self):
        super().setUp()
        self.enqueue("claude", "claude_ok.json", stderr="fake claude stderr\n")

    def _new_argv(self):
        self.send_ok("hello agent")
        return self.argvs("claude")[0]

    def test_new_turn_argv(self):
        # #36 agent table: claude -p <msg> --session-id <uuid> --permission-mode bypassPermissions --output-format json
        argv = self._new_argv()
        sid = argv[3] if len(argv) > 3 else None
        self.assertEqual(argv, ["-p", "hello agent", "--session-id", sid, "--permission-mode",
                                "bypassPermissions", "--output-format", "json"])

    def test_new_turn_session_id_is_uuid4(self):
        # #36: the driver generates the claude session id with uuid4
        argv = self._new_argv()
        self.assertEqual(uuid.UUID(argv[argv.index("--session-id") + 1]).version, 4)

    def test_records_the_uuid_it_passed(self):
        # #36 / #34 user story 47: claude's id is caller-chosen and recorded per label
        argv = self._new_argv()
        sid = argv[argv.index("--session-id") + 1]
        self.assertEqual(self.sessions()[LABEL], {"agent": "claude", "session_id": sid})

    def test_resume_turn_argv(self):
        # #36 agent table: claude -p <msg> --resume <id> --permission-mode bypassPermissions --output-format json
        argv = self._new_argv()
        sid = argv[argv.index("--session-id") + 1]
        self.send_ok("second message")
        self.assertEqual(self.argvs("claude")[1],
                         ["-p", "second message", "--resume", sid, "--permission-mode",
                          "bypassPermissions", "--output-format", "json"])

    def test_turn_runs_in_repo_dir(self):
        # #36 send: the agent-under-test's turn runs with cwd <repo-dir>
        self.send_ok("hello agent")
        self.assertEqual([os.path.realpath(c["cwd"]) for c in self.calls("claude")], [self.repo])

    def test_success_exits_0(self):
        # #36 send: exits 0 on success
        self.assertEqual(self.send("hello agent").returncode, 0)

    def test_prints_txt_path(self):
        # #36 send: prints the .txt path
        r = self.send_ok("hello agent")
        self.assertIn(self.log("smoke-1.txt"), [l.strip() for l in r.stdout.splitlines()])

    def test_writes_extracted_text(self):
        # #36: claude's final text is .result, written to <label>-<k>.txt
        self.send_ok("hello agent")
        self.assertEqual(_strip_nl(self.read(self.log("smoke-1.txt"))), CLAUDE_TEXT)

    def test_writes_user_message(self):
        # #36 send: <label>-<k>.user.txt holds the message
        self.send_ok("hello agent")
        self.assertEqual(_strip_nl(self.read(self.log("smoke-1.user.txt"))), "hello agent")

    def test_writes_raw_stdout(self):
        # #36 send: <label>-<k>.out holds the raw stdout
        argv = self._new_argv()
        with open(os.path.join(FIXTURES, "claude_ok.json")) as f:
            raw = f.read().replace("{SESSION_ID}", argv[argv.index("--session-id") + 1])
        self.assertEqual(self.read(self.log("smoke-1.out")), raw)

    def test_writes_stderr(self):
        # #36 send: <label>-<k>.err holds stderr
        self.send_ok("hello agent")
        self.assertEqual(self.read(self.log("smoke-1.err")), "fake claude stderr\n")

    def test_second_turn_is_numbered_2(self):
        # #36 send: turn k is 1-based per label
        self.send_ok("hello agent")
        self.send_ok("second message")
        self.assertEqual(_strip_nl(self.read(self.log("smoke-2.user.txt"))), "second message")

    def test_success_writes_no_failed_marker(self):
        # #36: the .failed marker is written only on failure
        self.send_ok("hello agent")
        self.assertFalse(os.path.exists(self.log("smoke-1.failed")))

    def test_creates_missing_nested_logs_dir(self):
        # #36 common options: --logs DIR is created if missing
        self.logs = os.path.join(self.tmp, "a", "b", "logs")
        self.send_ok("hello agent")
        self.assertTrue(os.path.exists(self.log("smoke-1.txt")))


class DefaultLogsTest(DriverCase):
    def test_default_logs_dir_is_smoke_logs(self):
        # #36 common options: --logs defaults to smoke/logs next to drive.py
        self.enqueue("claude", "claude_ok.json")
        default_logs = os.path.join(SMOKE, "logs")
        existed = os.path.isdir(default_logs)
        sessions = os.path.join(default_logs, "sessions.json")
        saved = None
        if os.path.exists(sessions):
            with open(sessions) as f:
                saved = f.read()
        label = "t36-default-logs-%d" % os.getpid()

        def restore():
            if not existed:
                shutil.rmtree(default_logs, True)
                return
            for name in os.listdir(default_logs):
                if name.startswith(label + "-"):
                    os.remove(os.path.join(default_logs, name))
            if saved is None:
                if os.path.exists(sessions):
                    os.remove(sessions)
            else:
                with open(sessions, "w") as f:
                    f.write(saved)
        self.addCleanup(restore)

        r = self.drive("send", label, self.repo, "hello agent", logs=False)
        self.assertTrue(os.path.exists(os.path.join(default_logs, label + "-1.txt")),
                        r.stdout + r.stderr)


class CursorSendTest(DriverCase):
    def setUp(self):
        super().setUp()
        self.enqueue("agent", "cursor_ok.json")

    def test_new_turn_creates_chat_then_resumes_it(self):
        # #36 agent table: agent create-chat, then agent -p <msg> --resume <id> --force --trust --output-format json
        self.send_ok("hello agent", "--agent", "cursor")
        self.assertEqual(self.argvs("agent"), [
            ["create-chat"],
            ["-p", "hello agent", "--resume", CURSOR_CHAT_ID, "--force", "--trust",
             "--output-format", "json"],
        ])

    def test_records_create_chat_id(self):
        # #36 / #34 user story 47: cursor's id is the stripped create-chat stdout
        self.send_ok("hello agent", "--agent", "cursor")
        self.assertEqual(self.sessions()[LABEL], {"agent": "cursor", "session_id": CURSOR_CHAT_ID})

    def test_resume_turn_reuses_chat(self):
        # #36 agent table: a later turn resumes the recorded chat without a new create-chat
        self.send_ok("hello agent", "--agent", "cursor")
        self.send_ok("second message", "--agent", "cursor")
        self.assertEqual(self.argvs("agent")[2:], [
            ["-p", "second message", "--resume", CURSOR_CHAT_ID, "--force", "--trust",
             "--output-format", "json"],
        ])

    def test_writes_extracted_text(self):
        # #36: cursor's final text is .result
        self.send_ok("hello agent", "--agent", "cursor")
        self.assertEqual(_strip_nl(self.read(self.log("smoke-1.txt"))), CURSOR_TEXT)


class CodexSendTest(DriverCase):
    def setUp(self):
        super().setUp()
        self.enqueue("codex", "codex_ok.jsonl")

    def test_new_turn_argv(self):
        # #36 agent table: codex exec --json --dangerously-bypass-approvals-and-sandbox <msg>
        self.send_ok("hello agent", "--agent", "codex")
        self.assertEqual(self.argvs("codex"),
                         [["exec", "--json", "--dangerously-bypass-approvals-and-sandbox", "hello agent"]])

    def test_records_thread_id_from_output(self):
        # #34 Implementation Decisions: codex id is thread.started -> thread_id
        self.send_ok("hello agent", "--agent", "codex")
        self.assertEqual(self.sessions()[LABEL], {"agent": "codex", "session_id": CODEX_THREAD_ID})

    def test_resume_turn_argv(self):
        # #36 agent table: codex exec resume <id> --json --dangerously-bypass-approvals-and-sandbox <msg>
        self.send_ok("hello agent", "--agent", "codex")
        self.send_ok("second message", "--agent", "codex")
        self.assertEqual(self.argvs("codex")[1],
                         ["exec", "resume", CODEX_THREAD_ID, "--json",
                          "--dangerously-bypass-approvals-and-sandbox", "second message"])

    def test_writes_last_agent_message(self):
        # #36: codex's final text is .item.text of the last agent_message item.completed
        self.send_ok("hello agent", "--agent", "codex")
        self.assertEqual(_strip_nl(self.read(self.log("smoke-1.txt"))), CODEX_TEXT)


class SendFailureTest(DriverCase):
    def test_nonzero_child_exit_makes_send_exit_1(self):
        # #36 send: exits 1 on a failed turn (claude: exit code must be 0)
        self.enqueue("claude", "claude_ok.json", exit=1)
        self.assertDeliberateExit(self.send("hello agent"), 1)

    def test_failed_turn_still_writes_the_four_files(self):
        # #36 send: the files are still written on a failed turn
        self.enqueue("claude", "claude_ok.json", exit=1, stderr="boom\n")
        self.send("hello agent")
        names = ["smoke-1.user.txt", "smoke-1.out", "smoke-1.err", "smoke-1.txt"]
        self.assertEqual([n for n in names if not os.path.exists(self.log(n))], [])

    def test_failed_turn_writes_failed_marker(self):
        # #36: send writes an empty <label>-<k>.failed marker on failure
        self.enqueue("claude", "claude_ok.json", exit=1)
        self.send("hello agent")
        self.assertEqual(self.read(self.log("smoke-1.failed")), "")

    def test_claude_is_error_is_failure(self):
        # #36: claude success requires .is_error not true
        self.enqueue("claude", "claude_is_error.json")
        self.assertDeliberateExit(self.send("hello agent"), 1)

    def test_claude_error_subtype_is_failure(self):
        # #36: claude success requires .subtype absent or "success"
        self.enqueue("claude", "claude_error_subtype.json")
        self.assertDeliberateExit(self.send("hello agent"), 1)

    def test_codex_turn_failed_is_failure(self):
        # #36: codex fails on a turn.failed event (exit code 0 here)
        self.enqueue("codex", "codex_turn_failed.jsonl")
        self.assertDeliberateExit(self.send("hello agent", "--agent", "codex"), 1)

    def test_codex_error_event_is_failure(self):
        # #36: codex fails on an error event even with turn.completed
        self.enqueue("codex", "codex_error_event.jsonl")
        self.assertDeliberateExit(self.send("hello agent", "--agent", "codex"), 1)


class StandInArgvTest(DriverCase):
    def test_claude_stand_in_argv(self):
        # #36 agent table: claude -p <prompt> --tools Read,Grep,Glob --permission-mode dontAsk --output-format json
        self.enqueue("codex", "codex_ok.jsonl")
        self.enqueue("claude", "claude_standin.json")
        self.send_ok("hello agent", "--agent", "codex")
        self.step_ok("--agent", "codex", "--stand-in", "claude")
        argvs = self.argvs("claude")
        prompt = argvs[0][1] if argvs and len(argvs[0]) > 1 else None
        self.assertEqual(argvs, [["-p", prompt, "--tools", "Read,Grep,Glob", "--permission-mode",
                                  "dontAsk", "--output-format", "json"]])

    def test_cursor_stand_in_argv(self):
        # #36 agent table: agent -p <prompt> --mode ask --trust --output-format json (new session, no create-chat)
        self.enqueue("claude", "claude_ok.json")
        self.enqueue("agent", "cursor_ok.json")
        self.send_ok("hello agent")
        self.step_ok("--stand-in", "cursor")
        argvs = self.argvs("agent")
        prompt = argvs[0][1] if argvs and len(argvs[0]) > 1 else None
        self.assertEqual(argvs, [["-p", prompt, "--mode", "ask", "--trust", "--output-format", "json"]])

    def test_codex_stand_in_argv(self):
        # #36 agent table: codex exec --json --sandbox read-only <prompt>
        self.enqueue("claude", "claude_ok.json")
        self.enqueue("codex", "codex_ok.jsonl")
        self.send_ok("hello agent")
        self.step_ok("--stand-in", "codex")
        argvs = self.argvs("codex")
        prompt = argvs[0][-1] if argvs and argvs[0] else None
        self.assertEqual(argvs, [["exec", "--json", "--sandbox", "read-only", prompt]])


class StepTest(DriverCase):
    """--agent codex --stand-in claude: the two different tools (#36 / #34 user story 44)."""

    def setUp(self):
        super().setUp()
        self.enqueue("codex", "codex_ok.jsonl")
        self.enqueue("claude", "claude_standin.json")

    def _step(self):
        self.send_ok("hello agent", "--agent", "codex")
        return self.step_ok("--agent", "codex", "--stand-in", "claude")

    def _prompt(self):
        self._step()
        argvs = self.argvs("claude")
        self.assertEqual(len(argvs), 1, "precondition: one stand-in call")
        return argvs[0][1]

    def test_stand_in_runs_in_smoke_folder(self):
        # #36 step: the stand-in's cwd is the folder containing drive.py
        self._step()
        self.assertEqual([os.path.realpath(c["cwd"]) for c in self.calls("claude")],
                         [os.path.realpath(SMOKE)])

    def test_prompt_names_stand_in_brief(self):
        # #36 step: the prompt holds the absolute path of smoke/STAND-IN.md
        self.assertIn(STAND_IN_MD, self._prompt())

    def test_prompt_names_latest_turn_text(self):
        # #36 step: the prompt holds the absolute path of the label's latest <label>-<k>.txt
        self.assertIn(self.log("smoke-1.txt"), self._prompt())

    def test_prompt_contains_goal(self):
        # #36 step: the prompt holds the goal text
        self.assertIn(GOAL, self._prompt())

    def test_prompt_asks_for_message_only(self):
        # #36 step: the prompt says "Reply with only the message to send"
        self.assertIn("Reply with only the message to send", self._prompt())

    def test_writes_stand_in_text(self):
        # #36 step: the stand-in's extracted text goes to <label>-<k>.standin.txt
        # (which k, the replied-to turn or the new one, is not pinned: #36 leaves it open)
        self._step()
        found = sorted(n for n in os.listdir(self.logs) if re.match(r"smoke-\d+\.standin\.txt$", n))
        self.assertEqual([_strip_nl(self.read(self.log(n))) for n in found], [STANDIN_TEXT])

    def test_sends_stand_in_text_to_agent_under_test(self):
        # #36 step: does what send does with the stand-in's text (codex resume turn)
        self._step()
        self.assertEqual(self.argvs("codex")[1:],
                         [["exec", "resume", CODEX_THREAD_ID, "--json",
                           "--dangerously-bypass-approvals-and-sandbox", STANDIN_TEXT]])

    def test_logs_stand_in_text_as_next_turn_message(self):
        # #36 step: the reply is turn 2's message
        self._step()
        self.assertEqual(_strip_nl(self.read(self.log("smoke-2.user.txt"))), STANDIN_TEXT)


class StepFailureTest(DriverCase):
    def setUp(self):
        super().setUp()
        self.enqueue("codex", "codex_ok.jsonl")
        self.enqueue("claude", "claude_standin.json", exit=1)

    def test_failed_stand_in_exits_1(self):
        # #36 step: exits 1 if the stand-in turn fails
        self.send_ok("hello agent", "--agent", "codex")
        self.assertDeliberateExit(self.step("--agent", "codex", "--stand-in", "claude"), 1)

    def test_failed_stand_in_sends_nothing(self):
        # #36 step: a failed stand-in sends nothing to the agent under test
        self.send_ok("hello agent", "--agent", "codex")
        self.step("--agent", "codex", "--stand-in", "claude")
        self.assertEqual(len(self.argvs("codex")), 1)


class LoopTest(DriverCase):
    """Agent under test: claude. Stand-in: codex, so stand-in calls are the codex calls."""

    STAND_IN = ("--stand-in", "codex")

    def test_asks_gh_for_slug_in_repo_dir(self):
        # #36 loop: gh repo view --json nameWithOwner -q .nameWithOwner, cwd <repo-dir>
        self.enqueue("claude", "claude_pr.json")
        self.send_ok("hello agent")
        self.loop(*self.STAND_IN)
        self.assertEqual([(c["argv"], os.path.realpath(c["cwd"])) for c in self.calls("gh")],
                         [(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], self.repo)])

    def test_pr_url_stops_with_exit_0(self):
        # #36 loop: a PR URL for the slug stops with exit 0
        self.enqueue("claude", "claude_pr.json")
        self.send_ok("hello agent")
        self.assertEqual(self.loop(*self.STAND_IN).returncode, 0)

    def test_pr_url_prints_stop_line(self):
        # #36 loop: prints "STOP <label>: pr <url>"
        self.enqueue("claude", "claude_pr.json")
        self.send_ok("hello agent")
        r = self.loop(*self.STAND_IN)
        self.assertIn("STOP smoke: pr " + PR_URL, [l.strip() for l in r.stdout.splitlines()])

    def test_pr_url_after_a_step_stops_after_that_step(self):
        # #36 loop: the check runs before each step, so a PR from step 1 ends the loop
        self.enqueue("claude", "claude_ok.json")
        self.enqueue("claude", "claude_pr.json")
        self.enqueue("codex", "codex_ok.jsonl")
        self.send_ok("hello agent")
        r = self.loop(*self.STAND_IN)
        self.assertEqual((r.returncode, len(self.argvs("codex"))), (0, 1), r.stdout + r.stderr)

    def test_pr_url_for_other_repo_is_ignored(self):
        # #36 loop: only https://github.com/<slug>/pull/<digits> stops it
        self.enqueue("claude", "claude_pr_other_repo.json")
        self.enqueue("claude", "claude_ok.json")
        self.enqueue("codex", "codex_ok.jsonl")
        self.send_ok("hello agent")
        self.assertEqual(self.loop("--max", "1", *self.STAND_IN).returncode, 2)

    def _failed_first_turn(self):
        self.enqueue("claude", "claude_ok.json", exit=1)
        self.enqueue("codex", "codex_ok.jsonl")
        self.assertDeliberateExit(self.send("hello agent"), 1, "precondition: failed send")

    def test_failed_turn_exits_1(self):
        # #36 loop: a failed latest turn stops with exit 1
        self._failed_first_turn()
        self.assertDeliberateExit(self.loop(*self.STAND_IN), 1)

    def test_failed_turn_prints_stop_error_line(self):
        # #36 loop: prints "STOP <label>: error <txt path>"
        self._failed_first_turn()
        r = self.loop(*self.STAND_IN)
        self.assertIn("STOP smoke: error " + self.log("smoke-1.txt"),
                      [l.strip() for l in r.stdout.splitlines()])

    def test_failed_turn_runs_no_step(self):
        # #36 loop: the check comes before the step
        self._failed_first_turn()
        self.loop(*self.STAND_IN)
        self.assertEqual(self.argvs("codex"), [])

    def _failing_stand_in(self):
        self.enqueue("claude", "claude_ok.json")
        self.enqueue("codex", "codex_ok.jsonl", exit=1)
        self.send_ok("hello agent")

    def test_failed_step_exits_1(self):
        # #36 loop: a failed step exits 1
        self._failing_stand_in()
        self.assertDeliberateExit(self.loop(*self.STAND_IN), 1)

    def test_failed_step_prints_stop_line(self):
        # #36 loop: prints "STOP <label>: step failed"
        self._failing_stand_in()
        r = self.loop(*self.STAND_IN)
        self.assertIn("STOP smoke: step failed", [l.strip() for l in r.stdout.splitlines()])

    def _plain_turns(self):
        self.enqueue("claude", "claude_ok.json")
        self.enqueue("codex", "codex_ok.jsonl")
        self.send_ok("hello agent")

    def test_max_steps_exits_2(self):
        # #36 loop: N steps with no stop exits 2
        self._plain_turns()
        self.assertEqual(self.loop("--max", "2", *self.STAND_IN).returncode, 2)

    def test_max_steps_prints_stop_line(self):
        # #36 loop: prints "STOP <label>: max steps"
        self._plain_turns()
        r = self.loop("--max", "2", *self.STAND_IN)
        self.assertIn("STOP smoke: max steps", [l.strip() for l in r.stdout.splitlines()])

    def test_max_bounds_the_number_of_steps(self):
        # #36 loop: --max N runs N steps
        self._plain_turns()
        self.loop("--max", "2", *self.STAND_IN)
        self.assertEqual(len(self.argvs("codex")), 2)

    def test_default_max_is_12(self):
        # #36 loop: --max defaults to 12
        self._plain_turns()
        self.loop(*self.STAND_IN)
        self.assertEqual(len(self.argvs("codex")), 12)


def _tree(root, skip=(".git", "__pycache__")):
    """{relative path: bytes} for files under root, skipping the `skip` folders."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                out[os.path.relpath(path, root)] = f.read()
    return out


class InitTest(DriverCase):
    def setUp(self):
        super().setUp()
        self.target = os.path.join(self.tmp, "smoke-repo")

    def init(self):
        return self.drive("init", SLUG, self.target)

    def init_ok(self):
        r = self.init()
        self.assertEqual(r.returncode, 0, "precondition: init failed\n" + r.stdout + r.stderr)
        return r

    def git(self, *args):
        return subprocess.run(["git", "-C", self.target] + list(args), env=self.env(),
                              capture_output=True, text=True)

    def test_copies_bundled_fixture(self):
        # #36 init: copies smoke/fixture/ to <dir>
        self.assertTrue(os.path.isdir(FIXTURE_PKG), "missing smoke/fixture/")
        self.init_ok()
        self.assertEqual(_tree(self.target), _tree(FIXTURE_PKG))

    def test_commits_on_main(self):
        # #36 init: git init -b main, git add -A, git commit
        self.init_ok()
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "main")

    def test_commit_includes_every_file(self):
        # #36 init: git add -A before the commit leaves a clean tree
        self.init_ok()
        self.assertTrue(os.path.isdir(os.path.join(self.target, ".git")), "precondition: no git repo")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all").stdout, "")

    def test_creates_private_github_repo(self):
        # #36 / #34 user story 39: gh repo create <owner/name> --private --source <dir> --push
        self.init_ok()
        self.assertEqual(self.argvs("gh"),
                         [["repo", "create", SLUG, "--private", "--source", self.target, "--push"]])

    def test_prints_setup_answers(self):
        # #36 init: prints the /setup-devflow-skills answers: GitHub, single-context, base branch main
        r = self.init_ok()
        missing = [w for w in ("GitHub", "single-context", "main") if w not in r.stdout]
        self.assertEqual(missing, [], r.stdout)

    def _fixture_tests(self):
        self.init_ok()
        self.assertTrue(os.path.isdir(self.target), "precondition: no repo dir")
        return subprocess.run(["python3", "-m", "unittest"], cwd=self.target, env=self.env(),
                              capture_output=True, text=True, timeout=120)

    def test_fixture_tests_pass(self):
        # #36 / #34 user story 40: the fixture's own tests pass under python3 -m unittest
        r = self._fixture_tests()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_fixture_has_tests(self):
        # #36 / #34 user story 40: python3 -m unittest finds at least one test in the fixture
        r = self._fixture_tests()
        self.assertRegex(r.stderr, r"Ran [1-9]\d* tests?")

    def _existing_target(self):
        os.makedirs(self.target)
        with open(os.path.join(self.target, "keep.txt"), "w") as f:
            f.write("mine\n")

    def test_existing_dir_exits_1(self):
        # #36 init: <dir> must not exist; if it does, exit 1
        self._existing_target()
        self.assertDeliberateExit(self.init(), 1)

    def test_existing_dir_is_left_untouched(self):
        # #36 init: an existing <dir> is not changed
        self._existing_target()
        self.assertDeliberateExit(self.init(), 1, "precondition")
        self.assertEqual(_tree(self.target, skip=()), {"keep.txt": b"mine\n"})

    def test_existing_dir_creates_no_github_repo(self):
        # #36 init: an existing <dir> changes nothing, including no gh repo create
        self._existing_target()
        self.assertDeliberateExit(self.init(), 1, "precondition")
        self.assertEqual(self.argvs("gh"), [])


if __name__ == "__main__":
    unittest.main()
