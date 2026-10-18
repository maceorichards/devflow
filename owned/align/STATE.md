# Run-state file

Location: `<main checkout>/.claude/docs/runs/iss-<N>.json` (`pending-<slug>.json` until #N exists). Git-ignored. Update it at every stage change, and after each ticket finishes, so a compacted or restarted session can resume with `/<workflow> #N`.

```json
{
  "workflow": "dev-single | dev-multi",
  "mode": "fast | rigor | mixed",
  "stage": "worktree | specced | aligned | ticketed | building | built | reviewed | finished",
  "issue": 42,
  "slug": "ca-buffer-model",
  "base_branch": "main",
  "branch": "feat/iss-42-ca-buffer-model",
  "worktree": "/abs/path/to/worktree",
  "spec_path": "/abs/path/.claude/docs/specs/iss-42-ca-buffer-model.md",
  "plan_paths": ["/abs/path/.claude/docs/plans/2026-10-17-iss-42-ca-buffer-model.md"],
  "baseline": {
    "command": "pytest -q",
    "passed": 118,
    "failed": 2,
    "failing_tests": ["tests/test_io.py::test_legacy_format", "tests/test_plot.py::test_dpi"]
  },
  "tickets": [
    {"number": 43, "title": "Interfaces + stubs", "lane": "fast", "status": "closed"},
    {"number": 44, "title": "Buffer kinetics", "lane": "rigor", "status": "open", "plan": "/abs/...", "branch": "feat/iss-42-ca-buffer-model--t44"}
  ],
  "spec_review_ran": false,
  "auto_approve_plans": false,
  "pr": null,
  "updated": "2026-10-17T10:12:00Z"
}
```

- `mode` is a property of the run. A resume with a different flag changes it from that point on, and the change is recorded here.
- Ticket `status` is one of `open`, `building`, `closed` or `needs-human`.
- `spec_review_ran` is set to `true` once `spec-review` has run on the feature branch (by `implement`, or by the workflow's final review). The final review uses it to avoid running `spec-review` twice.
- `auto_approve_plans` is `true` when the run was started with `--auto-approve-plans`, or the user said during the run to stop pausing for plan approval. Record that instruction here. A resume **without** `--auto-approve-plans` resets it to `false` and says so, so a waiver never carries over silently.
