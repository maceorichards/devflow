# devflow

A personal set of agent skills and workflows, built from upstream skill repos plus patches and owned skills, and installed for one or more agent tools.

## Language

**Provider**:
An agent tool that devflow installs into, such as Claude Code, Codex CLI, Gemini CLI or Cursor: a skills folder plus, where the tool reads one from disk, a global instructions file. Not the company whose model the tool runs.
_Avoid_: Target, harness, model provider

**Agent docs**:
The git-ignored working material agents write in a project's main checkout (specs, plans, run state and per-repo conventions), kept in `.devflow/`.
_Avoid_: Agent files, working docs
