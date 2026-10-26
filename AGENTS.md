# Contributor instructions

For agents working on the devflow repo itself, or on a fork of it. This file is never installed anywhere: what users get is the devflow section, `global/claude-md-section.md`.

## Rules

- **Tests:** run `python3 -m unittest` before calling a change done. Without the vendor clones most sync tests skip; `./sync.sh --dry-run` clones them without installing anything.
- **Patches:** change them only through `./sync.sh edit <skill>` (edit `.patch-work/<skill>/b/`), then `./sync.sh save <skill>` and `./sync.sh`. Never hand-edit a `patches/*.patch`.
- **Never edit an installed skill** (`<skills folder>/<name>/`). It's generated, and the next sync overwrites it. Change `owned/`, `patches/` or `manifest.json` here, then sync.
- **`vendor/`** holds the git-ignored upstream clones. Never edit or commit them.
- **Smoke driver exception:** when the user asks for an unattended smoke run, you may send devflow slash commands, and the answers to their pauses, as the user message of a headless child agent session in the throwaway smoke repo. Never in any other repo, and never in your own session. This is the one exception to the devflow section's "never start a slash-only skill yourself". The smoke kit is in `smoke/`; start with its README.

## Per-tool setup

Codex and Cursor read `AGENTS.md` natively. For the others:

- **Claude Code** reads `AGENTS.md` only when the repo has no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md`. If you keep one, put `@AGENTS.md` in it.
- **Gemini CLI:** add `AGENTS.md` to `context.fileName` in your settings, e.g. `"context": {"fileName": ["AGENTS.md", "GEMINI.md"]}`.

`CLAUDE.md`, `CLAUDE.local.md` and `GEMINI.md` are git-ignored here: keep your per-tool notes in them. Only `AGENTS.md` is shared.
