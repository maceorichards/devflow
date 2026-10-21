# devflow: design decisions

Why devflow is built the way it is. [SKILLS.md](SKILLS.md) says what is installed and how it runs; where the two disagree, SKILLS.md and the skills win. Each entry gives the decision, why, and what was rejected.

## 1. No session hook; two slash-only entry points

- **Decision:** no Superpowers session hook. The only heavy processes are `/dev-single` and `/dev-multi`, which only you can start.
- **Why:** rigorous planning when you ask for it, no ceremony when you don't. For small changes you just ask (optionally `/tdd`), and only auto-tier skills run.
- **Rejected:** the `using-superpowers` hook, which routes every session through its process skills.

## 2. Matt for alignment and parallel work, Superpowers for sequential rigor

- **Decision:** Matt's skills provide grilling, specs, tickets and parallel execution (`implement-spec`). Superpowers provides detailed plans, sequential reviewed execution (SDD), worktrees, verification and branch finishing.
- **Why:** each collection is strongest there, and a small handpicked set keeps the descriptions loaded into every session short.
- **Rejected (left out on purpose):**
  - Superpowers: `using-superpowers`, `brainstorming`, `executing-plans`, `test-driven-development` (replaced by `tdd`, see 6), `writing-skills`, `dispatching-parallel-agents`, `diagnosing-superpowers`.
  - Matt: `ask-matt`, `triage`, `improve-codebase-architecture`, `wayfinder`, `retro`, `handoff`, `teach`, `to-questionnaire`, `wait-what`, `wizard`, `writing-for-agents`.

## 3. Customizations are patches over pinned upstream clones

- **Decision:** upstream repos are git-ignored clones in `vendor/`, pinned in `vendor.lock`. Changes to upstream skills are patches, and `~/.claude/skills/` is generated output. If a patch stops applying after `--update`, that vendor's lock isn't advanced and the installed skills stay as they were.
- **Why:** updating is one command, and a customization is never silently dropped. The repo holds only your decisions and your own skills, so its history is a log of your choices.
- **Rejected:** copying upstream skills into the repo and editing them in place, which turns every upstream update into a manual merge.

## 4. Building blocks are sub tier, through narrowed descriptions

- **Decision:** skills that workflows call are "sub" tier: their `description` in `manifest.json` says to use them only when a workflow or skill calls for them, or when you ask.
- **Why:** `disable-model-invocation` also stops other skills from loading a skill (confirmed at install), so building blocks can't be slash-only.
- **Cost accepted:** the 22 auto and sub descriptions are loaded into every session, so each sub description is one short line.
- **Rejected:** `skillOverrides: name-only` in `settings.json` (untested, and not needed).

## 5. Agent working docs stay untracked, in the main checkout

- **Decision:** specs, plans and run state live in `<main checkout>/.claude/docs/`, git-ignored. The glossary and ADRs in `docs/` are tracked. Subagents get absolute paths, never pasted content.
- **Why:** these are working material for agents, not project history. Keeping them in one place that outlives worktrees makes resuming (`#N`) a file lookup. The local spec is what agents read and you edit; the GitHub issue is the lasting, shareable record and the fallback (`gh issue view N`).
- **Rejected:** keeping them inside the feature worktree, where they're deleted at finish and the resume lookup breaks.

## 6. `tdd` is owned, and the orchestrator launches the tester

- **Decision:** `tdd` was forked once from Matt's and is never re-synced (`owned/tdd/ORIGIN.md`). An independent tester subagent writes failing acceptance tests from the spec, then the implementer runs red-green. When the implementer is itself a subagent, the orchestrator launches its tester.
- **Why:** the independence comes from separating who writes the tests from who writes the code. Subagents can launch subagents here, but an implementer that launched its own tester would also write that tester's brief.
- **Rejected:** implementers launching their own testers.

## 7. The orchestrator never enters a worktree

- **Decision:** feature and ticket worktrees are plain `git worktree add <main>/.worktrees/…`. The orchestrating session stays in the main checkout and works in worktrees by absolute path (`git -C`, a subshell `(cd <wt> && …)`). `align` stops if it's started from a linked worktree.
- **Why:** a session inside a native worktree is isolated. Claude Code refuses its writes to the main checkout's `.claude/docs/`, and that check can't be turned off. The native tool also branches from `origin/<default>` under its own branch name, and `ExitWorktree` leaves a renamed branch behind.
- **Rejected:** Claude Code's native `EnterWorktree` (the original design), and moving agent docs into the worktree (see 5).

## 8. Per-repo setup commits nothing

- **Decision:** `/setup-devflow-skills` writes the `## Agent skills` block to the git-ignored `CLAUDE.local.md`, and the tracker and domain-doc conventions to `.claude/docs/agents/` (upstream's `docs/agents/`, moved by the manifest's `rewrite` map). Nothing is committed or pushed.
- **Why:** only the orchestrator reads these files, and it always runs in the main checkout (see 7), so worktrees and `origin` don't need them. `.claude/docs/` is already ignored globally, so no new ignore rule is needed, and repos that track their own `docs/agents/` are unaffected.
- **Cost accepted:** a fresh clone, another machine or a cloud session needs setup re-run.
- **Rejected:** committing the block to `CLAUDE.md` and the conventions to `docs/agents/` (the upstream behavior), and a global `docs/agents/` ignore rule.

## 9. SDD skips its own final review for devflow callers

- **Decision:** when `/dev-single --rigor` or `run-lanes` calls SDD, it skips its whole-branch Final Review and returns its deferred minor findings along with its Rulings.
- **Why:** the caller's final review (`spec-review` + `code-review` over the whole feature, with one fix pass) covers the same ground. In the smoke test, three reviews of one branch reached the same verdict. Per-task reviews still gate every task.
- **Rejected:** keeping SDD's final review and dropping `spec-review` in rigor mode.

## 10. Footprints stay per module; splits for parallelism are raised

- **Decision:** `to-tickets` lists each ticket's footprint as modules. If tickets can only run in parallel after a module is split, the proposal says so and asks: split or serialize.
- **Why:** in the smoke test, a one-file module was quietly turned into a package just so tickets could run in parallel, and review then flagged that as speculative generality. Asking keeps that architecture choice yours.
- **Rejected:** per-function footprints for fast tickets that only add new functions.

## 11. `--auto` uses a stand-in agent and ends at the PR

- **Decision:** `--auto` is the user's permission for one run to make the calls it would otherwise stop for. A fresh stand-in subagent answers the grilling rounds and reviews the spec; tickets, lanes and plans are approved; the PR opens without a confirmation, as a draft if work is blocked. Every call is logged and summarized in the PR. The rules live in one file, `owned/align/AUTO.md`, and each pause points to it.
- **Why:** separating who asks from who answers keeps grilling honest, and the log plus the PR review keep the user in control after the fact. Stopping at the PR leaves the merge to the user.
- **Rejected:** the orchestrator accepting its own recommendations (nobody pushes back), merging into main, auto carrying over to a resume without the flag, and letting `--auto` start slash-only skills such as `/dev-multi`.

## 12. ADRs are named by issue; a single-context glossary is headed by the repo name

- **Decision:** a new ADR is `docs/adr/iss-N-<slug>.md`, where N is the feature's issue. Existing numbered ADRs stay as they are. A single-context glossary's top heading is the repo name, never a feature's context name. `align`'s overlapping-PR check also flags open PRs that touch the glossary or ADRs.
- **Why:** in the smoke runs, parallel features collided on ADR numbers and glossary headings. Issue numbers are already unique, and a fixed heading leaves parallel branches differing only in their term entries.
- **Rejected:** sequential numbering (parallel branches pick the same number), reserving numbers at merge (a rename after review), and committing a glossary stub to the base branch (devflow commits nothing on base).

## 13. The base branch is asked for at setup

- **Decision:** `/setup-devflow-skills` asks which branch features start from and open PRs against, defaulting to the GitHub default branch, and records a `Base branch:` line in the tracker conventions (see 8). `align` reads that line; when it's missing, `align` falls back to the GitHub default and states that base in the first grilling round.
- **Why:** devflow used to assume the GitHub default silently, which is wrong for repos that work on `develop`. Asking once at setup costs one question; the fallback keeps repos set up earlier working, and stating the base lets you correct it.
- **Rejected:** always using the GitHub default branch, and asking on every run.

## 14. Fixes have a context budget

- **Decision:** every fix stays within a context budget. It edits an existing sentence, moves logic into a script, or moves text into a file loaded on demand (like `align`'s AUTO.md). Each changed skill file grows by about +30 words at most, measured with `wc -w` on the built skill.
- **Why:** every word in a SKILL.md is context the model carries through a run. Long skills are slower to follow and easier to misread, which caused several of the defects these fixes address.
- **Rejected:** a paragraph per fix.
