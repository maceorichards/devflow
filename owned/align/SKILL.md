---
name: align
description: "Devflow building block: the shared first half of /dev-single and /dev-multi (feature worktree, grill-with-docs, to-spec, spec review, run state). Use only when one of those workflows calls for it, or when the user asks for it by name."
---

# Align

The shared first half of every devflow workflow. It turns a feature description into: a feature branch in its own worktree, a resolved design (glossary + ADRs committed on that branch), a spec (GitHub issue #N + local spec file), the user's approval of the spec, and a run-state file the workflow can resume from.

The calling workflow tells you: its name (`dev-single` or `dev-multi`), its mode, whether auto mode is on, and either a feature description or `#N`. In auto mode, every pause below follows [AUTO.md](AUTO.md), and every skill you call is told it's a devflow auto run.

## Paths you will use

- **Main checkout:** `MAIN=$(git -C "$(git rev-parse --git-common-dir)/.." rev-parse --show-toplevel)`. Works from the main checkout and from any linked worktree.
- **Agent docs (git-ignored, always in the main checkout):** `$MAIN/.claude/docs/specs/`, `$MAIN/.claude/docs/plans/`, `$MAIN/.claude/docs/runs/`.
- **Feature worktree:** `WT=$MAIN/.worktrees/feat-<slug>` (the folder keeps this name after the branch is renamed).
- **Domain docs (tracked, on the feature branch):** `docs/GLOSSARY.md`, `docs/adr/`.

Always hand subagents **absolute paths** to specs, plans and state files. Never paste their content into a dispatch.

**The orchestrating session stays in the main checkout.** It never moves into the feature worktree (no `EnterWorktree`, no `cd` that persists). A worktree-isolated session can't write `$MAIN/.claude/docs/`, and no setting lifts that check. Work in the worktree through absolute paths: `git -C "$WT" …`, `uv run --directory "$WT" …`, or a subshell `(cd "$WT" && …)` for tools that need their working directory there.

## 0. Preflight

Check each of these, and stop with a clear message if one fails:

1. Inside a git repository whose `origin` is on GitHub, and `gh auth status` succeeds.
   - If this session is inside a **linked worktree** rather than the main checkout (detect as in `using-git-worktrees` Step 0), stop: "devflow runs from the main checkout. Reopen this session in `<main checkout>` and re-run."
2. `$MAIN/docs/agents/issue-tracker.md` exists. If not: "Run `/setup-devflow-skills` once in this repo (choose GitHub, single-context domain docs), then re-run."
   - These files are untracked and only the main checkout needs them, so nothing has to be committed or pushed. If the repo has only the old tracked `docs/agents` folder at its root, say so and ask the user to re-run `/setup-devflow-skills`, which moves it.
3. `git -C "$MAIN" check-ignore -q .claude/docs/x`. If `.claude/docs/` isn't ignored, warn the user (devflow normally ignores it globally) and offer to add it to the repo's `.gitignore`. (Auto mode: add it to `$MAIN/.git/info/exclude` instead.)
4. The working tree you start from has no uncommitted changes you would carry along. If it does, ask before continuing. (Auto mode: stop and report; this is a hard stop.)

## 1. Feature worktree first

Grilling writes tracked files, so the feature branch must exist *before* grilling.

1. **Slug:** kebab-case from the description, at most 40 characters.
2. **Base branch:** the repo's default branch (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`). Run `git fetch origin <base>`.
3. **Overlapping open PRs:** list open PRs (`gh pr list --state open --json number,title,files`) whose files the feature will likely touch. Mention them in the first grilling round (dependency on unmerged code, likely merge conflicts).
4. **Create the worktree:** call the Skill tool with `using-git-worktrees`. The user invoking the workflow is consent; don't ask again. Request branch `feat/<slug>` based on `origin/<base>`, created with:
   ```bash
   git -C "$MAIN" worktree add "$MAIN/.worktrees/feat-<slug>" -b feat/<slug> origin/<base>
   ```
   Never use the native `EnterWorktree` tool here (see "The orchestrating session stays in the main checkout").
5. **Baseline:** let `using-git-worktrees` run project setup and the test suite. Record the command and the pass/fail counts, plus the **names** of any failing tests.
6. Write the provisional state file `$MAIN/.claude/docs/runs/pending-<slug>.json` (schema in [STATE.md](STATE.md)), with stage `worktree`. In auto mode also set the `auto` fields and create the decision log `pending-<slug>-decisions.md` next to it.

## 2. Grill

Call the Skill tool with `grill-with-docs`, working inside the feature worktree. Glossary terms go in `docs/GLOSSARY.md`; ADRs go in `docs/adr/`. Continue until the user confirms a shared understanding. In auto mode, the stand-in agent in [AUTO.md](AUTO.md) answers each round and gives that confirmation.

## 3. Spec

Call the Skill tool with `to-spec`. Pass it the slug and tell it to use devflow spec storage. It creates issue **#N** and writes `$MAIN/.claude/docs/specs/iss-N-<slug>.md`.

Then:
- Rename the branch: `git branch -m feat/iss-N-<slug>`. The worktree folder keeps its name.
- Rename the state file to `runs/iss-N.json` (and any decision log to `runs/iss-N-decisions.md`), fill in `issue`, `spec_path` and `branch`, and set stage `specced`.

## 4. Commit the domain docs

If `docs/GLOSSARY.md` or `docs/adr/` changed:

```bash
git -C "$WT" add docs/GLOSSARY.md docs/adr
git -C "$WT" commit -m "docs(iss-N): <glossary | ADRs | glossary and ADRs>"
```

Name only what changed: `docs(iss-N): glossary`, `docs(iss-N): ADRs`, or `docs(iss-N): glossary and ADRs`.

This must happen before anything branches off the feature branch, because new worktrees only contain committed work.

## 5. Spec review (pause)

Give the user the spec file path and the issue URL. Ask them to review it, either by editing the file directly or by telling you what to change. **End your turn and wait.** (Auto mode: the stand-in reviews it instead, as in [AUTO.md](AUTO.md).)

- If they changed anything, call `to-spec` again in update mode, so the file and the issue match.
- **Escalation hint (`dev-single` only):** if the spec clearly contains several independently deliverable pieces, say so and suggest `/dev-multi #N` instead. (Auto mode: don't switch; log it for the PR's `## Auto decisions`.)

On approval, set stage `aligned`. Then return control to the calling workflow with: N, slug, spec path, branch, worktree path, base branch.

## Resume (`#N`)

When a workflow is invoked with `#N`:

1. Read `$MAIN/.claude/docs/runs/iss-N.json`.
2. **If it's missing, rebuild it:**
   - spec from `$MAIN/.claude/docs/specs/iss-N-*.md` (or the issue body),
   - branch from `git branch --list 'feat/iss-N-*'`,
   - worktree from `git worktree list`,
   - tickets from the issue's sub-issues.

   Tell the user what you reconstructed.
3. **If the branch exists but has no worktree,** re-create one for it: `git worktree add "$MAIN/.worktrees/feat-iss-N-<slug>" feat/iss-N-<slug>`.
4. Stay in the main checkout and work in the feature worktree by absolute path. If the recorded stage is earlier than `aligned`, continue from that stage of this skill; otherwise return to the workflow.
