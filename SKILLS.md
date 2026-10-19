# devflow skills: current overview

What is installed, what each skill does, and the names it uses. [DESIGN.md](DESIGN.md) records why; this file records what. Where they disagree, this file and the skills win.

## Quick start

1. **Once per repo:** `/setup-devflow-skills`. Choose GitHub and single-context domain docs. It writes the `## Agent skills` block to the git-ignored `CLAUDE.local.md` and the tracker and domain-doc conventions to the git-ignored `.claude/docs/agents/`. Nothing is committed.
2. **Open the Claude Code session in the main checkout,** not in a worktree. devflow creates and drives its own worktrees from there.
3. **Run a workflow:**

| Command | Use for |
|---|---|
| `/dev-single <description> [--fast \| --rigor] [--auto]` | One-ticket feature. `--rigor` adds an approved plan and subagent-driven execution; `--fast` is the default. |
| `/dev-multi <description> [--fast \| --rigor] [--auto]` | Multi-ticket feature with a lane per ticket. No lane flag means MIXED (lanes proposed per ticket). |
| `/dev-single #N`, `/dev-multi #N` (+ flags) | Resume issue N, change its mode, or upgrade single → multi. |
| just ask, or `/tdd` / `/tdd --solo` | Small changes, with no workflow. |

Flags are parsed strictly: an unknown flag (for example `--rigour`) is refused, and nothing runs. Each command states its mode before it does anything.

**`--auto`** is your permission for one run to make the calls it would otherwise stop for: a stand-in agent answers the grilling and reviews the spec, tickets, lanes and plans are approved, and the PR opens without a confirmation (as a draft if anything is blocked). Turn it on at the start, with `#N --auto` on a resume, or by saying so in chat at a pause. A resume without it turns it off. Hard stops (preflight, dirty tree, failing baseline, rejected push) still stop; merging, force-pushing and starting slash commands never happen. Every call is logged in `runs/iss-N-decisions.md` and summarized in the PR's `## Auto decisions`. The rules are in `align/AUTO.md`.

## Skill inventory (28)

**Tiers:** *slash* means only you can start it (6). *sub* means it runs when a workflow or skill calls it, or when you ask by name (17). *auto* means Claude may use it whenever it fits (5).

### Workflows and owned building blocks (`owned/`)

| Skill | Tier | What it does |
|---|---|---|
| `dev-single` | slash | One ticket: `align` → build (`implement`, or with `--rigor`: `writing-plans` + your approval + `subagent-driven-development`) → final review → PR. |
| `dev-multi` | slash | Several tickets: `align` → `to-tickets` (one approval for breakdown and lanes) → `run-lanes` → final review → PR. |
| `align` | sub | Shared first half: preflight → feature worktree → grilling + glossary/ADRs → spec → your spec review → run-state file. Also handles resume (`#N`). |
| `run-lanes` | sub | Lane engine for `/dev-multi`. Fast tickets are built in parallel through `implement-spec`; rigor tickets one at a time (plan → approval → SDD → local merge). Both land on one integration branch. |
| `tdd` | sub | Double-loop TDD. An independent tester subagent writes the failing acceptance tests first, then the implementer runs red-green cycles. Includes the passes-immediately rule. Forked once from Matt's `tdd`. |

### From mattpocock/skills

| Skill | Tier | What it does | devflow changes |
|---|---|---|---|
| `setup-devflow-skills` | slash | Per-repo setup: issue tracker, labels, domain-doc layout | **Renamed** from `setup-matt-pocock-skills`; block goes to `CLAUDE.local.md`; conventions go to `.claude/docs/agents/` (manifest `rewrite`); commits nothing; GitHub template trimmed to sub-issues and blocking |
| `grill-with-docs` | sub | Calls `grilling` + `domain-modeling` | description only |
| `grilling` | sub | Interviews you in rounds of numbered questions with recommended answers | description only |
| `domain-modeling` | sub | Challenges terms and writes `docs/GLOSSARY.md` and ADRs | patched: `docs/GLOSSARY.md` path |
| `to-spec` | sub | Spec → GitHub issue #N + local spec file | patched: devflow storage |
| `to-tickets` | sub | Spec → sub-issue tickets with native blocking, interfaces-first ticket, footprints, lanes, overlap check | patched |
| `implement` | sub | Builds one spec inline with `tdd`, then `spec-review` | patched |
| `implement-spec` | sub | Fast-lane tickets in parallel worktrees: a tester → implementer → merger for each ticket | patched |
| `spec-review` | sub | Two-axis review (repo standards, fit with the spec) using parallel subagents | Matt's `code-review`, renamed (it avoids clashing with the built-in `/code-review`) and patched |
| `codebase-design` | sub | Vocabulary for deep modules, interfaces and seams | description only |
| `diagnosing-bugs` | auto | Builds a feedback loop first, then works through ranked hypotheses | none |
| `research` | auto | Cited investigation against primary sources | none |
| `pr` | auto | PR body shape: summary, evidence, merge danger | none |
| `grill-me` | slash | Standalone alignment interview | none |
| `prototype` | slash | Throwaway prototype to answer a design question | none |

### From obra/superpowers

| Skill | Tier | What it does | devflow changes |
|---|---|---|---|
| `writing-plans` | sub | Spec (optionally one ticket) → an exact plan, task by task, with a Review Focus section | patched |
| `subagent-driven-development` (SDD) | sub | For each task: tester → fresh implementer → task review; keeps a ledger and records rulings | patched; skips its own final review for devflow callers |
| `requesting-code-review` | sub | Reviewer template used by SDD | description only |
| `using-git-worktrees` | sub | Creates or verifies a worktree, runs project setup, records baseline tests | patched; devflow always uses `.worktrees/` |
| `finishing-a-development-branch` | sub | Tests, then merge, PR or keep, after one confirmation | patched |
| `verification-before-completion` | auto | Full suite, every failure by name, compared with the baseline | patched |
| `receiving-code-review` | auto | Weighing review feedback | none |
| `systematic-debugging` | slash | Root cause first; after 3 failed fixes, question the architecture | patched |

## How the workflows run

**Session and worktree model.** The orchestrating session never leaves the main checkout. It works in worktrees by absolute path: `git -C <wt>`, `uv run --directory <wt>`, or a subshell `(cd <wt> && …)`. Claude Code's built-in worktree isolation (`EnterWorktree` and app-made worktree sessions) blocks writes to the main checkout's `.claude/docs/`, and no setting turns that off. So devflow never uses the native worktree tool, and `align` stops if it's started from a linked worktree. Subagents get absolute paths to specs, plans and state files.

**Ticket lanes (`/dev-multi`).**
- `fast`: built in parallel. For each ticket, a tester commits acceptance tests, then an implementer (with `tdd`) builds it, then a merger merges into the integration worktree, runs the suite and closes the ticket.
- `rigor`: built one at a time. `writing-plans` against the current integration tip → your approval (skipped in auto mode) → SDD in a ticket worktree → `finishing-a-development-branch` merges it locally → the ticket closes.
- The two lanes take turns. A rigor ticket's worktree is cut only after the fast batch has returned. A ticket becomes `needs-human` when SDD's fix loop can't resolve a finding, when an implementer is blocked twice, or when a merge fails its tests.
- **Interfaces-first ticket:** its stubs are the deliverable. Its tests pin only names, signatures and shared types, so they stay true after later tickets land.

**Reviews, in order.**
1. Every task or ticket: an independent tester writes the acceptance tests first, and implementers may never change them.
2. Rigor work: SDD runs a task review (spec compliance + quality) on every task.
3. Every feature: `spec-review` + the built-in `code-review` over the whole branch, then one fix subagent for Critical/Important findings. Minor findings go under Follow-ups in the PR.
4. `verification-before-completion`, compared with the baseline.
5. Push + PR, after one confirmation.

SDD's own whole-branch review is skipped for devflow callers, because step 3 covers it.

**Resume.** `/dev-single #N` or `/dev-multi #N` reads `runs/iss-N.json` and continues from the recorded stage. It rebuilds the file from the issue, spec, branch and worktrees if the file is missing. It first reports parent #N, the stage, the mode and the ticket table. A changed lane flag updates `mode` and re-labels only the tickets that are still open. A resume without `--auto` turns auto mode off and says so; `--auto` on a resume turns it on from that stage.

## Naming conventions

| Thing | Name |
|---|---|
| Feature (integration) branch | `feat/<slug>` until the issue exists, then `feat/iss-N-<slug>` |
| Feature worktree | `<main>/.worktrees/feat-<slug>` (the folder keeps this name after the branch rename) |
| Fast-ticket branch / worktree | `feat/iss-N-<slug>--t<T>` / `<main>/.worktrees/feat-<slug>--t<T>` |
| Rigor-ticket branch / worktree | `feat/iss-N-<slug>--t<T>` / `<main>/.worktrees/feat-iss-N-t<T>` |
| Spec | GitHub issue #N (label `ready-for-agent`) + `<main>/.claude/docs/specs/iss-N-<slug>.md` (authoritative for agents) |
| Tickets | GitHub sub-issues of #N, labels `ready-for-agent` + `lane:fast` or `lane:rigor` (`needs-human` when stuck), native `blocked_by` edges |
| Plan | `<main>/.claude/docs/plans/YYYY-MM-DD-iss-N[-t<T>]-<slug>.md` |
| Run state | `<main>/.claude/docs/runs/iss-N.json` (`pending-<slug>.json` before #N exists). Stages: `worktree → specced → aligned → ticketed → building → built → reviewed → finished` |
| SDD ledger | `<ticket or feature worktree>/.superpowers/sdd/<plan>/progress.md` |
| Domain-docs commit | `docs(iss-N): glossary`, `… ADRs` or `… glossary and ADRs` (only what changed) |
| Acceptance-test commit | `test(iss-N): …`, `test(iss-N-t<T>): …` or `test(<scope> task K): acceptance tests` |
| Implementation commit | `feat(iss-N[-t<T>]): <what>` |
| Ticket close comment | "Merged into feat/iss-N-<slug> at <sha>." (merge commit message is left to the merger) |
| PR body | `pr` template sections, then the ticket table (multi), `## Follow-ups`, and `Closes #N` (+ `Closes #T` for every closed ticket) |

## Where things live

| Location | Contents | Tracked? |
|---|---|---|
| `<repo>/CLAUDE.local.md` | `## Agent skills` block (tracker, domain docs) | no (global ignore) |
| `<repo>/docs/GLOSSARY.md`, `docs/adr/` | domain language and ADRs, committed on the feature branch | yes |
| `<repo>/.claude/docs/` | specs, plans, run state (and auto-mode decision logs), setup's tracker and domain-doc conventions in `agents/` (main checkout only) | no (global ignore) |
| `<repo>/.worktrees/` | feature and ticket worktrees | no (global ignore) |
| `~/.claude/skills/` | installed skills, generated by `./sync.sh` (never edit there) | n/a |
| `~/.claude/CLAUDE.md` | devflow section between `devflow` markers, from `global/claude-md-section.md` | n/a |
| `~/.config/git/ignore` | `.claude/docs/`, `.worktrees/`, `.claude/worktrees/`, `CLAUDE.local.md` | n/a |

## Known gaps

- The two ticket-worktree naming schemes above (fast vs rigor) differ. This is cosmetic.
