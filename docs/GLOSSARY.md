# devflow

An opinionated set of agent skills and workflows, built from upstream skill repos plus patches and owned skills, and installed for one or more agent tools. Use it as is, or fork it to choose your own skills.

## Language

**Provider**:
An agent tool that devflow installs into, such as Claude Code, Codex CLI, Gemini CLI or Cursor: a skills folder plus, where the tool reads one from disk, a global instructions file. Not the company whose model the tool runs.
_Avoid_: Target, harness, model provider

**Agent docs**:
The git-ignored working material agents write in a project's main checkout (specs, plans, run state and per-repo conventions), kept in `.devflow/`.
_Avoid_: Agent files, working docs

**Devflow section**:
The managed block that devflow writes into each provider's global instructions file, between `devflow` markers. It is for everyone who uses devflow, so nothing about developing devflow itself belongs in it.
_Avoid_: Global rules, managed block

**Contributor instructions**:
The tracked `AGENTS.md` at the root of the devflow repo, read by agents working on devflow itself (and on forks of it). Never installed anywhere.
_Avoid_: Project rules, dev rules

**Smoke run**:
An unattended end-to-end run of a devflow workflow in a throwaway repo, with a stand-in agent answering the workflow's pauses, used to find defects in the skills.
_Avoid_: Smoke test, e2e test
