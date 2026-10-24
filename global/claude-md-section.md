<!-- devflow:start (managed by ~/Documents/CUSTOM-SKILLS/devflow: edit global/claude-md-section.md there, then run sync.sh) -->
## devflow skills and workflows

- `/dev-single <description | #N> [--fast | --rigor] [--auto]`: one-ticket feature. Worktree → grill-with-docs → to-spec → your review → implement (or, with `--rigor`, plan + subagent-driven-development) → final review → PR.
- `/dev-multi <description | #N> [--fast | --rigor] [--auto]`: multi-ticket feature. Same first half → to-tickets with a fast or rigor lane per ticket → run-lanes onto one integration branch → final review → PR.
- `#N` resumes or upgrades the run for GitHub issue N.
- `--auto`: the run makes its own calls (a stand-in agent answers the grilling; specs, tickets and plans are approved) and ends at an open PR. A resume without `--auto` turns it off.
- Small changes: just ask, optionally with `/tdd` (or `/tdd --solo`).

Rules:
- **Tool wording:** "Call the Skill tool with X" means load and follow skill X, "dispatch a subagent" means use your tool's subagent feature, and `/name` means the user invoking skill `name` in your tool's syntax. If you cannot dispatch subagents, stop and say so; never fake a dispatch.
- **Never start a slash-only skill yourself:** `dev-single`, `dev-multi`, `grill-me`, `prototype`, `setup-devflow-skills`, `systematic-debugging`. `--auto` is the user's permission for that one run's pauses, nothing more: it never lets you start one of these.
- **Smoke driver exception:** when the user asks for an unattended smoke run, you may send these commands, and the answers to their pauses, as the user message of a child `claude -p` session in the throwaway smoke repo. Never in any other repo, and never in your own session.
- **Devflow building blocks run only when a workflow or another skill calls for them, or when the user asks:** align, grill-with-docs, grilling, domain-modeling, to-spec, to-tickets, implement, implement-spec, run-lanes, writing-plans, subagent-driven-development, requesting-code-review, using-git-worktrees, finishing-a-development-branch, spec-review, codebase-design, tdd.
- **Agent docs** live in the main checkout's git-ignored `.devflow/`:
  - specs: `specs/iss-N-<slug>.md`
  - plans: `plans/`
  - run state: `runs/iss-N.json`

  Give subagents absolute paths, never pasted content.
- **Repo conventions** (issue tracker, domain docs) live in `<repo>/.devflow/agents/`; read them when a skill refers to the issue tracker or domain docs.
- **Domain docs:** the glossary is `docs/GLOSSARY.md` and ADRs are in `docs/adr/`. Any skill that mentions `GLOSSARY.md` means `docs/GLOSSARY.md`.
- **Test reporting:** name every failure, and separate new failures from pre-existing ones.
<!-- devflow:end -->
