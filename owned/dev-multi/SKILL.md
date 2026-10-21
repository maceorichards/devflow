---
name: dev-multi
description: "Build a multi-ticket feature end to end: grill-with-docs → to-spec → your review → to-tickets with a fast or rigor lane per ticket → one approval → run-lanes onto one integration branch → final review → PR."
argument-hint: "<feature description | #N> [--fast | --rigor] [--auto]"
disable-model-invocation: true
---

# /dev-multi

Arguments: `$ARGUMENTS`

## 1. Parse arguments (strictly)

- **Allowed flags:** `--fast`, `--rigor`, `--auto`. `--fast` and `--rigor` are mutually exclusive.
  - Any other token starting with `-` → reply `Unknown flag <token>. /dev-multi accepts --fast, --rigor, --auto.` and **stop**.
  - Both `--fast` and `--rigor` → say so and stop.
- A token matching `#<digits>` means **resume or upgrade issue N**. Everything else is the feature description.
- No description and no `#N` → ask for a one-line feature description and stop.
- **Mode:**
  - `--fast` → FAST: every ticket's lane is pre-filled `fast`.
  - `--rigor` → RIGOR: every ticket's lane is pre-filled `rigor`.
  - Neither → MIXED: lanes are proposed per ticket.
- **`--auto`:** the user's permission for this run to make the calls it would otherwise stop for. Follow `align`'s [AUTO.md](../align/AUTO.md).
- State the mode in one line before doing anything else, adding `, AUTO` when auto mode is on.

**Resuming (`#N`):** follow the Resume section of the `align` skill, whose report states the changes below; then make them and continue from the recorded stage. If the mode differs from the state file's, update it. A mode change only re-labels tickets that are still `open`. `--auto` turns auto mode on from the current stage. If the state has `auto: true` and this invocation lacks `--auto`, reset it to `false`.

**Upgrading from `/dev-single`:** if the state file says `dev-single` and no build has started, switch it to `dev-multi` and continue at step 3.

## 2. Align

Call the Skill tool with `align` (workflow `dev-multi`, this mode, whether auto mode is on, the description). It returns once the user has approved the spec.

## 3. Tickets (stage `ticketed`)

Call the Skill tool with `to-tickets`. Pass:
- `#N` and the absolute spec path,
- the lane pre-fill (`fast`, `rigor`, or none for per-ticket proposals),
- the lane heuristics file: `~/.claude/skills/run-lanes/lane-heuristics.md`,
- in auto mode: "This is a devflow auto run; follow `align`'s AUTO.md at any pause." It then approves its own proposal (recommended lanes, overlaps resolved, splits serialised) and logs it.

`to-tickets` proposes all of the following and gets **one approval** for the breakdown and lanes together:
- vertical slices with blocking edges,
- an interfaces-first ticket,
- a module-level footprint for each ticket,
- a lane and one-line reason for each ticket,
- an overlap check among fast tickets that could run at the same time.

It then publishes the tickets as sub-issues of #N, labeled `ready-for-agent` and `lane:fast` or `lane:rigor`.

Record every ticket's number, title and lane in the state file.

## 4. Build (stage `building`)

Call the Skill tool with `run-lanes`. Pass: `#N`, the absolute spec path, the integration branch and worktree (the feature branch from `align`), the state file path, and whether auto mode is on.

It returns once every ticket is closed or marked `needs-human`. Set stage `built`.

If any tickets are `needs-human`, show them to the user and ask whether to finish anyway (the PR will list them as open) or stop here so the user can resolve them and resume with `/dev-multi #N`. (Auto mode: finish anyway, and open the PR as a draft.)

## 5. Final review (stage `reviewed`; by absolute path, never `cd`), on the integration branch

Let `BASE=$(git -C "$WT" merge-base origin/<base> HEAD)`, where `$WT` is the integration worktree.

1. Call the Skill tool with `spec-review`, using fixed point `BASE` and the absolute spec path. Set `spec_review_ran: true` in the state file.
2. Call the Skill tool with the built-in `code-review` on the same range.
3. Dispatch **one** fix subagent, in the integration worktree, with all Critical and Important findings, except any that target acceptance tests: those go under `## Follow-ups` as rulings for the user and don't count as remaining in step 6. Minor findings go into the PR description under "Follow-ups".
4. Call the Skill tool with `verification-before-completion`: full suite, every failure by name, compared with the baseline.

## 6. Finish (stage `finished`)

Call the Skill tool with `finishing-a-development-branch`, preselecting **option 2 (push + PR)** against `<base>`.
- It asks the user one confirmation first. (Auto mode: no confirmation. A draft PR if any ticket is `needs-human`, verification failed, or Critical/Important findings remain after the fix.)
- The PR body follows the `pr` skill's sections, then appends the ticket table, a `## Follow-ups` section (Minor findings, open rulings) and the closing lines for #N and every closed ticket (`Closes #N`, `Closes #T`…). Tickets still marked `needs-human` are listed as open, not closed. In auto mode, add `## Auto decisions` after `## Follow-ups` (see `align`'s AUTO.md).

Record the PR URL in the state file. Report: the PR URL, the ticket table (lane and outcome for each), test evidence, the SDD rulings from the rigor tickets, and follow-ups.
