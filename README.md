# devflow

An opinionated set of agent skills and workflows for Claude Code, Codex, Gemini CLI or Cursor: handpicked skills from [obra/superpowers](https://github.com/obra/superpowers) and [mattpocock/skills](https://github.com/mattpocock/skills), patches to some of them, and devflow's own skills, built into the skills folders of the providers you pick (Claude Code by default) so every project sees them. **[SKILLS.md](SKILLS.md) is the current overview** of every skill, the workflow mechanics and the naming conventions. [DESIGN.md](DESIGN.md) records why it's built this way.

Use it as is, or fork it to choose your own skills: edit `manifest.json`, then run `./sync.sh`.

## Quickstart

**Prerequisites:** Python 3.9+, git, the GitHub CLI `gh` signed in (`gh auth login`), and one supported provider (see [Providers](#providers)). GitHub is the only tracker the workflows support.

```bash
git clone https://github.com/maceorichards/devflow.git
cd devflow
./sync.sh --dry-run
./sync.sh
```

The dry run clones the upstream skill repos into `vendor/` at the locked commits and shows what would change, writing nothing outside the clone. The second command builds and installs for Claude Code; to pick other providers, run `./sync.sh providers <list>` instead. Then, in each project, run `/setup-devflow-skills` once (see [Workflows](#workflows)).

What the sync edits outside the clone:
- Each selected provider's skills folder (e.g. `~/.claude/skills`): only folders it marks with `.managed-by-devflow`. A folder of the same name without the marker is skipped.
- The devflow section of each provider's instructions file (e.g. `~/.claude/CLAUDE.md`), between `devflow` markers. The rest of the file is left alone.
- The git ignore file git reads, to which it appends the lines in `global/git-ignore-lines` (`.devflow/`, `.worktrees/`, …): the global `core.excludesFile`, else `$XDG_CONFIG_HOME/git/ignore`, else `~/.config/git/ignore`. A system-level `core.excludesFile` is not consulted.

## Workflows

| Command | Use for |
|---|---|
| `/dev-single <description> [--fast \| --rigor] [--auto]` | One-ticket feature, built in its own worktree and ending in a PR. `--rigor` adds a reviewed plan and subagent-driven execution; `--fast` is the default. |
| `/dev-multi <description> [--fast \| --rigor] [--auto]` | Multi-ticket feature. Each ticket gets a fast lane (parallel) or rigor lane (plan + reviewed subagents), with one approval for tickets and lanes together. |
| `/dev-single #N`, `/dev-multi #N` (+ flags) | Resume a run (or upgrade single → multi) for GitHub issue N. |
| *(optional W0)* just ask, or `/tdd` / `/tdd --solo` | Small changes. Only the auto-tier skills run. |

**`--auto`** (either command, at the start or on a resume `#N --auto`, or "go auto from here" in chat at a pause): the run makes its own calls instead of stopping for you. A stand-in agent answers the grilling and reviews the spec; tickets, lanes and plans are approved; the PR opens without a confirmation, as a draft if anything is blocked. Every call is logged in `runs/iss-N-decisions.md` and summarized under `## Auto decisions` in the PR. It never merges, force-pushes or starts a slash command, and a resume without `--auto` turns it off. Details: `owned/align/AUTO.md`.

**Once per repo:** run `/setup-devflow-skills`, choosing GitHub and single-context domain docs (`docs/GLOSSARY.md`, `docs/adr/`). It writes the tracker and domain-doc conventions to the git-ignored `.devflow/agents/`. It commits nothing, and writes no `CLAUDE.local.md` block. `setup-devflow-skills` is Matt Pocock's `setup-matt-pocock-skills`, renamed and patched; the manifest's `rewrite` map renames every upstream mention, and moves `docs/agents/` to `.devflow/agents/`, at build time.

**Already set up a repo?** Re-run `/setup-devflow-skills`, or `mv .claude/docs .devflow`, and delete the old `## Agent skills` block from `CLAUDE.local.md`.

**Where things live in a project:**
- `.devflow/` (git-ignored, main checkout): specs `specs/iss-N-<slug>.md`, plans `plans/`, run state `runs/iss-N.json`, setup's conventions `agents/`.
- `docs/GLOSSARY.md` and `docs/adr/`: tracked.
- `.worktrees/`: git-ignored feature and ticket worktrees. The orchestrating session never enters them; it stays in the main checkout.

## Providers

Pick which agents get the skills: `./sync.sh providers claude,codex` (add `--dry-run` to preview). The choice is local, in the git-ignored `devflow.local.json`; with no file, only `claude` is installed.

| Provider | Skills folder | Instructions file (devflow section) |
|---|---|---|
| `claude` | `~/.claude/skills` | `~/.claude/CLAUDE.md` |
| `codex` | `~/.agents/skills` | `~/.codex/AGENTS.md` |
| `gemini` | `~/.agents/skills` | `~/.gemini/GEMINI.md` |
| `cursor` | `~/.agents/skills` | none: paste `global/claude-md-section.md` into Customize → Rules (the sync reminds you) |

Codex, Gemini and Cursor share `~/.agents/skills`. For Codex, slash-tier skills also get `agents/openai.yaml` with `allow_implicit_invocation: false`.

Cursor also reads `~/.claude/skills` and `~/.codex/skills`, so with Claude or Codex selected next to Cursor it sees skills twice, and duplicates can appear. Select Cursor alone, or accept them.

Deselecting a provider removes its devflow skills (folders with a `.managed-by-devflow` marker) and its devflow section. Cleanup skips symlinked skill folders, folders that are the same directory as one still installed to, and instructions files whose `devflow` markers are malformed.

## Tiers

| Tier | Meaning | How it's set |
|---|---|---|
| auto | Claude may use it whenever it fits | upstream frontmatter |
| sub | runs when a workflow or another skill calls for it, or when you ask | narrowed `description` in `manifest.json` |
| slash | only when you type it | `disable-model-invocation: true` |

The building blocks can't be slash-only: `disable-model-invocation` also stops other skills from loading them.

## Repo layout

| Path | What |
|---|---|
| `SKILLS.md` | What is installed and how the workflows run |
| `DESIGN.md` | Why: the design decisions and what was rejected |
| `manifest.json` | Every managed skill (source, upstream path, tier, description override, patch) and the providers table |
| `devflow.local.json` | Which providers this machine installs to (git-ignored; written by `./sync.sh providers`) |
| `vendor.lock` | The upstream commits the patches were last applied against (written by `sync.sh`) |
| `patches/` | Diffs against upstream skills |
| `owned/` | devflow's own skills. Never synced from upstream. `tdd` was forked once from Matt Pocock's (see `owned/tdd/ORIGIN.md`). |
| `global/` | The devflow section for providers' instructions files (between `devflow` markers) and the global git ignore lines |
| `tests/` | The `python3 -m unittest` suite for `sync.sh` and the docs |
| `vendor/` | Git-ignored upstream clones |
| `sync.sh`, `lib/sync.py` | The build-and-install tool |

## Commands

```bash
./sync.sh              # rebuild + install everything at the locked commits
./sync.sh --dry-run    # show what would change
./sync.sh --update     # pull upstream, show changes per skill, rebuild, re-lock
./sync.sh providers <list> [--dry-run] # choose providers (claude,codex,gemini,cursor), then sync
./sync.sh edit <skill> # prepare .patch-work/<skill>/{a,b} to change a patch; edit b/
./sync.sh save <skill> # write patches/<skill>.patch from .patch-work/<skill>, then ./sync.sh
python3 -m unittest    # run the test suite
```

**Safety rules:**
- `sync.sh` only touches folders in the providers' skills folders that contain a `.managed-by-devflow` marker.
- If a patch stops applying after `--update`, that vendor's lock isn't advanced and the installed skills stay as they were. Re-port the patch with `edit` / `save`, then run `--update` again.

**Adding a skill:** add an entry to `manifest.json`, then run `./sync.sh`. **Removing one:** delete its entry; `./sync.sh` removes the installed copy.

**Never edit an installed `<skills folder>/<name>/` directly.** It's generated, and the next sync overwrites it.

## Contributing

Agents (and people) working on devflow itself, or on a fork, follow [AGENTS.md](AGENTS.md): the test command, the patch edit/save flow and the rules for the repo. To check the workflows end to end, use the smoke kit: [smoke/README.md](smoke/README.md).
