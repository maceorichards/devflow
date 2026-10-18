---
name: dev-single
description: "Build a single-ticket feature end to end in its own worktree: grill-with-docs → to-spec → your review → implement (or --rigor: plan + subagent-driven development) → final review → PR."
argument-hint: "<feature description | #N> [--rigor]"
disable-model-invocation: true
---

# /dev-single

Arguments: `$ARGUMENTS`

## 1. Parse arguments (strictly)

- **Allowed flag:** `--rigor`. Any other token starting with `-` (for example `--rigour`, `--fast`) → reply `Unknown flag <token>. /dev-single accepts only --rigor.` and **stop**.
- A token matching `#<digits>` means **resume or upgrade issue N**. Everything else is the feature description.
- No description and no `#N` → ask for a one-line feature description and stop.
- Before doing anything else, state the mode in one line, for example: `/dev-single, FAST mode, new feature: "<description>"` or `/dev-single, RIGOR mode, resuming #42`.

**Resuming (`#N`):** follow the Resume section of the `align` skill, then continue from the recorded stage.
- If the state file's `mode` differs from this invocation's mode, update it and say so.
- If the run already has tickets (it was a `/dev-multi` run), stop and tell the user to continue with `/dev-multi #N`.
- **Report the resume** before continuing: parent `#N` and its title, the recorded stage, the mode (and any change), a ticket table (number, title, lane, status) when the run has tickets, and what happens next. Never refer to a ticket number in a way that could read as a different feature.

## 2. Align

Call the Skill tool with `align` (workflow `dev-single`, this mode, the description). It returns once the user has approved the spec. The spec issue #N **is** the ticket.

## 3. Build (stage `building`), inside the feature worktree

**FAST (default):** call the Skill tool with `implement`. Pass the absolute spec path and `#N`.
- `tdd` runs in main-session mode, so it launches its own tester subagent.
- `implement` ends with `spec-review`. Set `spec_review_ran: true` in the state file.

**RIGOR (`--rigor`):**
1. Call the Skill tool with `writing-plans`. Pass the absolute spec path, and the plan path `$MAIN/.claude/docs/plans/<YYYY-MM-DD>-iss-N-<slug>.md`. The execution method is already chosen: subagent-driven development.
2. Show the user the plan path. **End your turn and wait for approval.** Apply any requested changes to the plan first.
3. Call the Skill tool with `subagent-driven-development`. Pass the plan path and the working directory (the feature worktree). It runs a tester before each task, then the implementer, then the task review, and finally its whole-branch review.
4. When it reaches its Finish step, it **returns here** rather than running `finishing-a-development-branch`.
5. Carry its "Rulings I made" list into your final report.

Set stage `built`.

## 4. Final review (stage `reviewed`)

Let `BASE=$(git merge-base origin/<base> HEAD)`.

1. If the state file's `spec_review_ran` is `false` (RIGOR mode), call the Skill tool with `spec-review`. Use fixed point `BASE` and the absolute spec path. Then set it to `true`.
2. Call the Skill tool with the built-in `code-review` (correctness bugs) on the branch diff against `BASE`.
3. If the reviews found Critical or Important issues, dispatch **one** fix subagent with the complete findings list and the spec path. Minor findings go into the PR description under "Follow-ups".
4. Call the Skill tool with `verification-before-completion`: full suite, every failure by name, compared with the baseline in the state file.

## 5. Finish (stage `finished`)

Call the Skill tool with `finishing-a-development-branch`, preselecting **option 2 (push + PR)** against `<base>`.
- It asks the user **one confirmation** before pushing; the user may pick merge or keep instead.
- The PR body follows the `pr` skill's sections, then appends a `## Follow-ups` section (the Minor findings and any rulings left open) and the line `Closes #N`.

Record the PR URL in the state file. Report: the PR URL, test evidence, rulings (RIGOR mode), and follow-ups.
