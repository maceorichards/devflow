---
name: tdd
description: "Test-driven development with a double loop: an independent tester subagent writes failing acceptance tests from the spec, then the implementer runs red-green cycles. Use when the user wants test-first work, invokes /tdd, or a devflow workflow or implementer calls for it."
argument-hint: "[--solo]"
---

# Test-Driven Development (double loop)

TDD is the red → green loop. This version adds an **outer loop**: acceptance tests written by an **independent tester subagent** that has never seen the implementation. Inside it runs the usual **inner loop** of small red-green cycles. Every section applies on every cycle.

When exploring the codebase, read `docs/GLOSSARY.md` (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in `docs/adr/` in the area you're touching.

## Which mode am I in?

- **Main-session mode:** you are the top-level session (the user typed `/tdd`, or `implement` called this skill in `/dev-single`). **You launch the tester yourself** (Outer loop, below), then run the inner loop.
- **Implementer mode:** you are a subagent dispatched by an orchestrator (`implement-spec`, `subagent-driven-development`). The orchestrator already ran the tester. Don't launch one. Instead:
  1. Find the acceptance-test commit (`test(...): acceptance tests`) your dispatch names.
  2. Run those tests and confirm they **fail for the right reason**: an assertion, `NotImplementedError` from a stub, or the existing code doing the wrong thing (wrong value, wrong exception, no exception). Never an import, syntax or fixture error, except in an **interfaces-first ticket**, where the missing names (ImportError/AttributeError) are the expected red state. If any pass, follow **The passes-immediately rule** and report it to the orchestrator before continuing.
  3. Run the inner loop until they pass.
- **`--solo`:** for tiny changes the user explicitly marks with `/tdd --solo`. Skip the tester; run the inner loop alone. The passes-immediately rule still applies.

## Seams: agree them first

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** Before any test is written, write down the seams under test and confirm them with the user (main-session mode), **unless the spec already records agreed seams** (devflow specs do, under Testing Decisions): then take them from the spec without asking again. In implementer mode, take them from the spec, plan or ticket. Give each proposed seam a one-line note on what it catches and what it misses.

When the shape of an interface is itself in question (how deep the module is, where the seam belongs, what the interface should expose), call the Skill tool with `codebase-design` for the vocabulary. It is a reference to consult, not a session to run.

If the repo has no test framework, propose one (pytest for Python) and ask before adding it. In a devflow auto run, add the recommended one and log it (`align`'s AUTO.md).

## Outer loop: the tester subagent (main-session mode)

1. **Write a test brief** using [tester-brief.md](tester-brief.md). It contains:
   - the behavior,
   - the public interfaces (exact signatures),
   - the agreed seams,
   - edge cases and failure modes,
   - the **source of each expected value**,
   - numerical tolerances with justifications.

   It describes **behavior only, never an implementation approach**. Save it to a temporary file outside the repo. If a spec exists, give the tester the spec's absolute path too.
2. **Dispatch the tester** with the prompt in [tester-brief.md](tester-brief.md). Use a capable model; test quality is the point. The tester:
   - creates interface stubs that raise `NotImplementedError` (unless they exist already, or the ticket is interfaces-first, where the stubs are the implementer's deliverable),
   - writes black-box acceptance tests,
   - confirms **every one fails for the right reason**,
   - commits them on their own (`test(<scope>): acceptance tests`),
   - reports the test names and why each one fails.
3. **Check the report.** Re-run the tests yourself and confirm they're red. Then start the inner loop.

Without a spec, the brief comes from the same session that will implement. So the independence comes from separating **who writes the tests** from **who writes the code**. Keep the brief strictly behavioral.

## Inner loop: implementer rules

- **Red before green.** Write a failing test at an agreed internal seam (or start from a failing acceptance test), then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Don't touch the acceptance tests.** Never modify, delete, skip or loosen a test from the acceptance-test commit. If one looks wrong, **stop and flag it** with evidence: the test, the spec line, and why you think it's wrong. The orchestrator or the user decides. Reviewers check `git diff <acceptance-commit>..HEAD` on those files.
- **Targeted runs only.** During the loop, run the current test file plus the acceptance tests. The full suite belongs to `verification-before-completion` at the end of the slice or ticket.
- **Refactoring is not part of the loop.** It belongs to review (`spec-review`).

## The passes-immediately rule (both loops)

A new test that **passes before the code it covers exists** is a red flag. Stop and state one of these reasons:

- **The behavior already exists.** It's a characterization test that pins down current behavior. Keep it and label it as such.
- **A regression test for a bug that's already fixed.** Keep it.
- **A refactor:** the test guards behavior that must not change. Keep it.
- **None of the above:** the test is broken. Typical causes: a wrong import, the target mocked away, an assertion that checks nothing, or testing the stub. Fix the test until it fails for the right reason.

When the reason is doubtful, run a **mutation check**: temporarily break the code the test covers (return a wrong value, delete a branch), confirm the test fails, then restore the code and confirm it passes.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification and survives refactors because it doesn't care about internal structure.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Anti-patterns

- **Implementation-coupled:** mocks internal collaborators, tests private methods, or verifies through a side channel (for example, querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological:** the assertion recomputes the expected value the way the code does, so it passes by construction. Expected values must come from an **independent source**: a known-good literal, a worked example, an analytic solution, a published result, or the spec.
- **Horizontal slicing in the inner loop:** writing all the internal tests first, then all the implementation. The acceptance tests are the deliberate exception: few, black-box, at agreed seams, and derived from the spec.
- **Unjustified tolerances:** a numerical assertion with a tolerance chosen to make it pass. State where the tolerance comes from (discretization error, float precision, measurement noise).
