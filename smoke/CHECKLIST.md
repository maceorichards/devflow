# devflow smoke checklist

What each scenario of a [smoke run](README.md) should show. Re-run after changing workflows or patches, in a fresh repo from `drive.py init`, and use a new label per scenario. Tick items from the logs, the smoke repo's files and commits, and its issues and PRs.

## 0. Setup: `/setup-devflow-skills`
- [ ] Asks for the tracker; for GitHub, asks which base branch features start from and fills the `Base branch:` line in `.devflow/agents/issue-tracker.md`
- [ ] Writes the conventions to `.devflow/agents/` (`issue-tracker.md`, `domain.md`); writes no instructions file and no `## Agent skills` block; no root `docs/agents/`; commits nothing
- [ ] Domain docs single-context: `docs/GLOSSARY.md` and `docs/adr/`
- [ ] `.devflow/x` and `.worktrees/x` are ignored (`git check-ignore -q`)
- [ ] Tracker doc has "Sub-issues and blocking", no `/wayfinder` or `/triage`
- [ ] First workflow run passes `align` preflight with nothing pushed beyond the initial commit

## 1. `/dev-single` (fast)
- [ ] Mode line comes first
- [ ] Base is `main`, read from the `Base branch:` line (stated in the first grilling round only when that line is missing)
- [ ] Worktree `.worktrees/feat-<slug>` cut from `origin/main`; the session stays in the main checkout
- [ ] Branch renamed `feat/<slug>` → `feat/iss-N-<slug>` after to-spec; folder name kept
- [ ] Issue #N with `ready-for-agent`; `.devflow/specs/iss-N-<slug>.md` exists with its `<!-- spec for #N` header and is ignored
- [ ] State file `.devflow/runs/iss-N.json` (renamed from `pending-<slug>.json`)
- [ ] Glossary's top heading is the repo name; any ADR is `docs/adr/iss-N-<slug>.md`
- [ ] Domain-docs commit message names only what changed, or no commit if nothing changed
- [ ] Seams taken from the spec, not asked a second time
- [ ] `test(...)` commit lands before `feat(...)`; tests fail for the right reason
- [ ] Test comments cite `#N` / user story, never the local spec path
- [ ] Acceptance tests untouched after the tester commit
- [ ] Passes-immediately rule fires on pre-existing behavior that has no test yet
- [ ] Final review: `spec-review` with three parallel axes (Standards, Spec, Correctness), one fix pass for Critical and Important findings, then verification against the baseline. No other review step.
- [ ] One confirmation before push; PR against `main`; body has `## Follow-ups` and `Closes #N`

## 2. `/dev-single --rigor`
- [ ] Plan in `.devflow/plans/<date>-iss-N-<slug>.md`; turn ends for plan approval
- [ ] Tester before each SDD task, committed first
- [ ] SDD skips its own final review and returns its deferred minors + Rulings
- [ ] SDD commands run as `(cd <dir> && …)`; the session's working directory never flips into the worktree
- [ ] `spec-review` runs once, at the final review

## 3. `/dev-multi --fast` (3 tickets)
- [ ] One approval for tickets + lanes: interfaces-first ticket, footprints, lane reasons, overlap check
- [ ] Interfaces-first criteria are names and signatures only; its tester writes no stubs
- [ ] Tickets are sub-issues of #N with `## Spec (devflow)`, `## Lane (devflow)` and `## Footprint (devflow)`; the ready set counts open blockers from the edge list
- [ ] Ticket worktrees cut from the integration tip; independent tickets run in parallel
- [ ] Merger merges in the integration worktree, runs the suite, closes the ticket; worktrees removed; merged ticket branches deleted with `-d`
- [ ] Final review is `spec-review` on the integration branch
- [ ] PR closes #N and every ticket

## 4. `/dev-multi` mixed (one rigor ticket)
- [ ] Lanes proposed per ticket from `lane-heuristics.md`; overlap check covers rigor/fast pairs
- [ ] Fast batch first; the rigor worktree is cut only after it returns
- [ ] Rigor plan in `.devflow/plans/<date>-iss-N-t<T>-<slug>.md`, written against the current integration tip; turn ends for approval

## 5. Resume `/dev-multi #N --rigor` in a fresh session (new label)
- [ ] Resume report: parent #N, stage, mode, ticket table, next step, before any state change
- [ ] Mode switch re-labels open tickets only; pending plan reused
- [ ] "Go auto from here" at the plan pause sets `auto` (`auto_source: chat`); the rest runs unattended
- [ ] Opened outside the repo: asks for the repo path, doesn't search the disk

## 6. Flags
- [ ] `/dev-single --rigour <desc>` refused with `Unknown flag --rigour. /dev-single accepts --fast, --rigor, --auto.`; nothing created
- [ ] `/dev-single <desc> --fast --rigor` refused; `--auto-approve-plans` is an unknown flag

## 7. `--auto`
- [ ] `/dev-single <desc> --fast --auto`: mode line says AUTO; no questions until the PR opens
- [ ] A stand-in subagent answers each grilling round and reviews the spec; `.devflow/runs/iss-N-decisions.md` logs every call
- [ ] PR body has `## Auto decisions` after `## Follow-ups`; nothing merged, nothing force-pushed
- [ ] `/dev-multi <desc> --fast`: grill normally, then `/dev-multi #N --auto` at the spec pause → tickets approved and built unattended
- [ ] A blocked ticket (or findings left after the fix pass) → draft PR listing it
- [ ] Resume an auto run without `--auto` → says auto is off and pauses again

## 8. Other agents (`--agent cursor` or `codex`)
- [ ] devflow installed for that provider (`./sync.sh providers …`); Cursor has the devflow section in its rules
- [ ] Subagents really dispatch (Codex needs `multi_agent = true`); a tool that can't says so and stops, never fakes one
- [ ] Codex doesn't start slash-tier skills on its own (`agents/openai.yaml`)

## Watch for
- Missing subagent report files: the controller backfills them. Verify commits, not hand-back text.
- A `.txt` holds only the turn's final message, so text written earlier in the turn (a resume report, say) may be missing from it. Check the effects (state file, commits, issues) instead.
