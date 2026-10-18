<!-- devflow:start (managed by ~/Documents/CUSTOM-SKILLS/devflow: edit global/claude-md-section.md there, then run sync.sh) -->
## devflow skills and workflows

- `/dev-single <description | #N> [--rigor]`: one-ticket feature. Worktree → grill-with-docs → to-spec → your review → implement (or, with `--rigor`, plan + subagent-driven-development) → final review → PR.
- `/dev-multi <description | #N> [--fast | --rigor]`: multi-ticket feature. Same first half → to-tickets with a fast or rigor lane per ticket → run-lanes onto one integration branch → final review → PR.
- `#N` resumes or upgrades the run for GitHub issue N.
- Small changes: just ask, optionally with `/tdd` (or `/tdd --solo`).

Rules:
- **Never start a slash-only skill yourself:** `dev-single`, `dev-multi`, `grill-me`, `prototype`, `setup-devflow-skills`, `systematic-debugging`.
- **Devflow building blocks run only when a workflow or another skill calls for them, or when the user asks:** align, grill-with-docs, grilling, domain-modeling, to-spec, to-tickets, implement, implement-spec, run-lanes, writing-plans, subagent-driven-development, requesting-code-review, using-git-worktrees, finishing-a-development-branch, spec-review, codebase-design, tdd.
- **Agent docs** live in the main checkout's git-ignored `.claude/docs/`:
  - specs: `specs/iss-N-<slug>.md`
  - plans: `plans/`
  - run state: `runs/iss-N.json`

  Give subagents absolute paths, never pasted content.
- **Domain docs:** the glossary is `docs/GLOSSARY.md` and ADRs are in `docs/adr/`. Any skill that mentions `GLOSSARY.md` means `docs/GLOSSARY.md`.
- **Test reporting:** name every failure, and separate new failures from pre-existing ones.
<!-- devflow:end -->
