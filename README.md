# devflow

My Claude Code skills and workflows. **[SKILLS.md](SKILLS.md) is the current overview** of every skill, the workflow mechanics and the naming conventions. Handpicked skills from [obra/superpowers](https://github.com/obra/superpowers) and [mattpocock/skills](https://github.com/mattpocock/skills), plus my patches and my own skills, built into `~/.claude/skills/` so every project sees them. [DESIGN.md](DESIGN.md) records why it's built this way.

## Workflows

| Command | Use for |
|---|---|
| `/dev-single <description> [--rigor]` | One-ticket feature, built in its own worktree and ending in a PR. `--rigor` adds a reviewed plan and subagent-driven execution. |
| `/dev-multi <description> [--fast \| --rigor]` | Multi-ticket feature. Each ticket gets a fast lane (parallel) or rigor lane (plan + reviewed subagents), with one approval for tickets and lanes together. |
| `/dev-single #N`, `/dev-multi #N` | Resume a run (or upgrade single → multi) for GitHub issue N. |
| *(optional W0)* just ask, or `/tdd` / `/tdd --solo` | Small changes. Only the auto-tier skills run. |

**Once per repo:** run `/setup-devflow-skills`, choosing GitHub and single-context domain docs (`docs/GLOSSARY.md`, `docs/adr/`). It writes the `## Agent skills` block to the git-ignored `CLAUDE.local.md` and the tracker and domain-doc conventions to the git-ignored `.claude/docs/agents/`. It commits nothing. `setup-devflow-skills` is Matt Pocock's `setup-matt-pocock-skills`, renamed and patched; the manifest's `rewrite` map renames every upstream mention, and moves `docs/agents/` to `.claude/docs/agents/`, at build time.

**Where things live in a project:**
- `.claude/docs/` (git-ignored, main checkout): specs `specs/iss-N-<slug>.md`, plans `plans/`, run state `runs/iss-N.json`, setup's conventions `agents/`.
- `docs/GLOSSARY.md` and `docs/adr/`: tracked.
- `.worktrees/`: git-ignored feature and ticket worktrees. The orchestrating session never enters them; it stays in the main checkout.
- `CLAUDE.local.md`: git-ignored, holds the `## Agent skills` block.

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
| `manifest.json` | Every managed skill: source, upstream path, tier, description override, patch |
| `vendor.lock` | The upstream commits the patches were last applied against (written by `sync.sh`) |
| `patches/` | Diffs against upstream skills |
| `owned/` | My skills. Never synced from upstream. `tdd` was forked once from Matt's (see `owned/tdd/ORIGIN.md`). |
| `global/` | The `~/.claude/CLAUDE.md` section (between `devflow` markers) and the global git ignore lines |
| `vendor/` | Git-ignored upstream clones |
| `sync.sh`, `lib/sync.py` | The build-and-install tool |

## Commands

```bash
./sync.sh              # rebuild + install everything at the locked commits
./sync.sh --dry-run    # show what would change
./sync.sh --update     # pull upstream, show changes per skill, rebuild, re-lock
./sync.sh edit <skill> # prepare .patch-work/<skill>/{a,b} to change a patch; edit b/
./sync.sh save <skill> # write patches/<skill>.patch from .patch-work/<skill>, then ./sync.sh
```

**Safety rules:**
- `sync.sh` only touches folders in `~/.claude/skills/` that contain a `.managed-by-devflow` marker.
- If a patch stops applying after `--update`, that vendor's lock isn't advanced and the installed skills stay as they were. Re-port the patch with `edit` / `save`, then run `--update` again.

**Adding a skill:** add an entry to `manifest.json`, then run `./sync.sh`. **Removing one:** delete its entry; `./sync.sh` removes the installed copy.

**Never edit `~/.claude/skills/<name>/` directly.** It's generated, and the next sync overwrites it.
