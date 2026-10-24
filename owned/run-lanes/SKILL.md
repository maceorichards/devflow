---
name: run-lanes
description: "Devflow building block: build a ticketed spec onto one integration branch, with fast-lane tickets in parallel (implement-spec) and rigor-lane tickets sequentially (writing-plans + subagent-driven-development). Use only when /dev-multi calls for it, or when the user asks for it by name."
---

# Run lanes

You receive:
- `#N` and the absolute spec path,
- the integration branch `feat/iss-N-<slug>` and its worktree (`INT_WT`),
- the run-state file,
- whether auto mode is on (`auto` in the state file; see `align`'s AUTO.md). In auto mode, tell every skill you call: "This is a devflow auto run; follow `align`'s AUTO.md at any pause."

Every ticket is a sub-issue of #N, labeled `lane:fast` or `lane:rigor`.

`MAIN=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)`

## Ground rules

- **Only committed work is visible to new worktrees.** Before every batch and every rigor ticket, the integration worktree must be clean (`git -C "$INT_WT" status --porcelain` empty). If it isn't, stop and report.
- **Ticket branches** are named `feat/iss-N-<slug>--t<M>` and are always cut from the **current tip of the integration branch**.
- **Give subagents absolute paths** (spec, plan, state file, worktree), never pasted content.
- **Nothing is ever force-pushed, discarded or deleted** except ticket worktrees this run created under `$MAIN/.worktrees/` and their ticket branches, after the branch has merged (`branch -d`, never `-D`).
- **Stay in the main checkout.** Drive worktrees by absolute path (`git -C`, `uv run --directory`, subshell `cd`).
- **Update the state file** after every ticket changes status.

## Ready set

A ticket is **ready** when it is open and every ticket blocking it is closed. Read the blocking edges from GitHub's native dependencies, using the **edge list**, not `issue_dependencies_summary` (the summary lags for several seconds after edges are added):

```bash
gh api repos/{owner}/{repo}/issues/<T>/dependencies/blocked_by --jq '[.[] | select(.state=="open")] | length'
```

A result of `0` means no open blockers. If the endpoint isn't available, read the ticket's `Blocked by` section instead.

## Loop

Repeat until every ticket is `closed` or `needs-human`:

### 1. Fast batch

If any **ready `lane:fast`** ticket exists, call the Skill tool with `implement-spec` in **sub-run mode**. Pass:
- the absolute spec path,
- the integration branch and `INT_WT`,
- the list of `lane:fast` ticket numbers it may take (all open fast tickets; it works through their dependency frontier itself),
- the instruction: "sub-run mode: do not open a PR, do not run the final review; return when no eligible ticket is ready."

It closes tickets as they merge. Afterwards, refresh the ready set.

When every ticket is `lane:fast`, this one step builds everything.

### 2. Rigor tickets, one at a time

For each **ready `lane:rigor`** ticket `T`, highest unblock count first (tickets that unblock others go first):

1. **Plan:** call the Skill tool with `writing-plans`. Pass the absolute spec path and ticket `#T`, and save to `$MAIN/.devflow/plans/<YYYY-MM-DD>-iss-N-t<T>-<slug>.md`. Plan against the **current** integration branch, since earlier tickets may have changed the code.
2. **Approval:** unless the state file has `auto: true`, show the user the plan path and **end your turn and wait**. Apply any requested changes first. If the user says to go auto from here, set the `auto` fields as in `align`'s AUTO.md. In auto mode, approve the plan and log its path in the decision log.
3. **Worktree:** cut it only after the fast batch has returned, so it starts from a tip that includes every merged fast ticket.
   ```bash
   git -C "$MAIN" worktree add "$MAIN/.worktrees/feat-iss-N-t<T>" -b "feat/iss-N-<slug>--t<T>" "feat/iss-N-<slug>"
   ```
4. **Execute:** call the Skill tool with `subagent-driven-development`. Pass the plan path and the working directory (that worktree). It runs a tester before each task, then the implementer and the task review, then its whole-branch review. It returns to you at its Finish step. Keep its "Rulings I made" list for the final report.
5. **Merge:** call the Skill tool with `finishing-a-development-branch`, preselecting **option 1 (merge locally)** with base `feat/iss-N-<slug>`. The integration branch is checked out in `INT_WT`, so the merge runs there. Run the suite on the merged result. In auto mode, finishing skips its confirmation.
6. **Close:** `gh issue close <T> --comment "Merged into feat/iss-N-<slug> at <sha>."` Then remove the ticket worktree (finishing does this for `.worktrees/` paths) and delete the merged ticket branch from the integration worktree, so `-d` checks it against the integration branch rather than `main`: `git -C "$INT_WT" branch -d feat/iss-N-<slug>--t<T>`.

### 3. Refresh

Recompute the ready set and update the state file. If nothing is ready but open tickets remain, every remaining ticket is blocked by a `needs-human` ticket: stop the loop.

## Failure handling

A ticket becomes **`needs-human`** when any of these happens:
- SDD's fix-loop breaker trips with a load-bearing finding it can't rule on,
- an implementer is `BLOCKED` twice,
- a merge into the integration branch fails its tests.

When that happens:
1. Label it: `gh issue edit <T> --add-label needs-human`.
2. Comment why: `gh issue comment <T> --body "<why>"`.
3. Leave its branch and worktree in place.
4. Continue with the tickets it doesn't block.

## Return

Return to `/dev-multi` with:
- the ticket table: number, title, lane, outcome, merge commit,
- all SDD rulings,
- `needs-human` tickets with reasons,
- the integration branch's head commit.

## Known limitation

The two lanes take turns rather than running at the same time: SDD runs in this session's context, and `implement-spec` returns before rigor work starts.
