# devflow smoke kit

A **smoke run** is an unattended end-to-end run of a devflow workflow in a throwaway repo. The agent under test runs the workflow in a headless session; a stand-in agent answers its pauses, as the user would. It finds defects in the skills that the offline suite can't: a step skipped, a path wrong, a pause that never comes.

| File | What |
|---|---|
| `drive.py` | The driver: `init`, `send`, `step`, `loop` (run with `--help` for each) |
| `agents.json` | The per-agent command table |
| `fixture/` | The throwaway repo's starting content: `tally`, a tiny stdlib-only Python package tested with `python3 -m unittest` |
| `CHECKLIST.md` | What each scenario should show |
| `STAND-IN.md` | The stand-in's brief |
| `logs/` | Every turn's input and output (git-ignored) |

## Cost and safety

A smoke run costs real usage. Every `send` and `step` is a live, full agent turn on your account, and a workflow turn with its subagents can take many minutes; each `step` adds a stand-in call. A whole `/dev-multi` scenario runs tens of turns. It also creates a real private GitHub repo, with issues, branches and PRs.

The agent under test runs with its bypass flag (claude `--permission-mode bypassPermissions`, cursor `--force`, codex `--dangerously-bypass-approvals-and-sandbox`), so it runs any command without asking, as you. Only ever point it at a throwaway repo made by `init`, never at a repo you care about. The stand-in runs with its read-only flags, from `smoke/`. The contributor instructions ([AGENTS.md](../AGENTS.md)) allow an agent to drive smoke runs only in the throwaway smoke repo.

## Prerequisites

- `python3`, `git`, and `gh` logged in (`gh auth status`) with permission to create repos.
- The CLI of each agent you use, logged in: `claude`, `agent` (Cursor) or `codex`.
- devflow installed for the agent under test: `./sync.sh providers <list>` (Cursor: paste the devflow section into its rules). Re-sync after every change you want to test: the run uses the installed skills, not this checkout.

## A run, end to end

From the devflow repo:

```bash
# 1. Create the throwaway repo from the fixture. It prints the setup answers.
python3 -I smoke/drive.py init <you>/devflow-smoke ~/smoke/devflow-smoke
SMOKE=~/smoke/devflow-smoke

# 2. Per-repo setup in the agent under test, then let the stand-in answer its questions.
python3 -I smoke/drive.py send setup "$SMOKE" "/setup-devflow-skills"
python3 -I smoke/drive.py step setup "$SMOKE" "Finish setup with the answers in your brief."

# 3. A scenario: start the workflow, then loop until a PR opens.
python3 -I smoke/drive.py send single "$SMOKE" "/dev-single let top_words skip a list of stop words"
python3 -I smoke/drive.py loop single "$SMOKE" "Approve the spec and the push. Keep the scope to top_words." --max 15
```

- **Labels** (`setup`, `single`) name a session: the first `send` for a label starts one, later turns resume it. Use a new label for a fresh session, for example to test a resume (`/dev-multi #N`).
- **`step`** answers one pause; repeat it as needed. **`loop`** repeats `step` until the reply holds a PR URL for the smoke repo (exit 0), a turn fails (exit 1) or `--max` steps ran (exit 2, default 12). After a stop, read the logs, then `send` your own message or run `loop` again.
- **The goal** tells the stand-in how to steer: which lane a ticket gets, when to say "go auto from here", which flag to try. Put workflow flags in the message you `send`, for example `/dev-multi <description> --fast`.
- **Scenarios** are the sections of [CHECKLIST.md](CHECKLIST.md); tick its items from the logs and the repo.

## Reading the logs

Turn `k` of a label writes to `smoke/logs/` (or `--logs DIR`):

| File | What |
|---|---|
| `<label>-<k>.user.txt` | The message sent |
| `<label>-<k>.txt` | The reply's text: the turn's final message only |
| `<label>-<k>.out`, `.err` | The agent's raw stdout and stderr |
| `<label>-<k>.failed` | Empty marker: the turn failed |
| `<label>-<k>.standin.*` | The stand-in's reply to this turn |
| `sessions.json` | The session id and agent for each label |

Check the effects too: commits, `.devflow/` in the smoke repo, and its issues and PRs on GitHub.

## Choosing agents

Every subcommand takes `--agent NAME` (the agent under test) and `--stand-in NAME` (the stand-in's agent), both defaulting to `claude`. They are independent, so you can test Codex with a Claude stand-in: `python3 -I smoke/drive.py loop single "$SMOKE" "<goal>" --agent codex --stand-in claude`. A label stays with the agent it started with.

| Agent | Status |
|---|---|
| `claude` | Verified |
| `cursor` | Verified. As a stand-in, `--mode ask` isn't confirmed as a hard read-only lock in print mode; the brief also forbids edits. |
| `codex` | **Unverified** until a smoke run passes with it. Needs `multi_agent = true` for subagents. |

Gemini has no entry yet.

## Adding an agent

Add one entry to `agents.json`:

- `session`: how a new session gets its id: `caller` (the driver picks a uuid and passes it), `create` (run the `create` command first; its stdout is the id), or `output` (the agent reports it).
- `new`, `resume`, `stand_in`: argv templates. `{msg}` and `{id}` fill one element each; `{bypass}` and `{read_only}` splice in the `bypass` and `read_only` flag lists.
- `output`: where the reply text and session id are, and how failure shows: `json` (one object) or `jsonl` (events).
- `verified`: `false` until a smoke run has passed with it.

Then add recorded sample outputs to `tests/fixtures/smoke/` and cover the entry in `tests/test_smoke_driver.py`, which runs the driver against fake CLIs.

## Results

Results stay out of the repo: `logs/` is git-ignored, and transcripts are never committed. A finding worth keeping becomes a GitHub issue on devflow, with the scenario, the turn and what went wrong. When you're done, delete the throwaway repo (`gh repo delete <you>/devflow-smoke`) and its folder.
