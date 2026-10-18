# Tester brief and dispatch prompt

The orchestrator (main session, `implement-spec`, or `subagent-driven-development`) writes a **brief**, saves it to a file, and dispatches the tester with the **prompt** below. The tester never sees implementation code written for this ticket or task.

## Brief template

```markdown
# Test brief: <ticket/task title>

Spec: <absolute spec path, or "none: session brief">
Ticket/task: <#T, or plan path + "Task K">
Working directory: <absolute worktree path>
Commit message scope: <iss-N-tT | iss-N task K | short-name>

## Behavior to pin
<what callers must observe: inputs → outputs/effects, in domain terms (docs/GLOSSARY.md)>

## Public interfaces (exact)
<signatures: module path, name, parameters with types, return type, errors raised>
<say which already exist and which need stubs>

## Seams under test
<the agreed seams, each with "catches / misses">

## Cases
- Normal: <...>
- Edge / failure modes: <...>  (include the plan's Review Focus lines when there is a plan)

## Expected values and their sources
| Case | Expected | Source (literal / worked example / analytic / published / spec line) |

## Tolerances
<numerical tolerances and why: discretization order, float precision, noise>

## Test conventions
<framework, file locations, naming, fixtures already in the repo>
```

## Dispatch prompt

```
You are the TESTER for <ticket/task>. Read your brief first: <BRIEF_PATH>
<if spec> The spec is the authority: <SPEC_PATH> </if>

Your job is acceptance tests that pin the required behavior BEFORE anyone implements it.

Rules:
- Do not read or rely on implementation code written for this ticket/task. Read only the
  existing public interfaces, the test conventions, the spec and the brief.
- Write stubs for interfaces that don't exist yet: the exact signatures from the brief,
  with bodies that raise NotImplementedError (or the language's equivalent). Nothing else.
  Exception: in an interfaces-first ticket the stubs ARE the deliverable. Write none, and
  pin only what stays true after later tickets land (names, parameters, shared types),
  never "raises NotImplementedError". The expected failure is then ImportError/AttributeError.
- Write black-box tests at the agreed seams only, through public interfaces. One logical
  assertion per test. Name tests by behavior.
- Expected values come only from the sources in the brief, never from running code.
  State tolerances and their justification in a comment.
- When a comment cites the spec, cite the issue (`#N`, user story k), never a local spec
  path: devflow specs are git-ignored and won't exist for other readers.
- No mocks of internal collaborators. Mock only true system boundaries (network, clock,
  randomness, external services).
- Run the new tests. EVERY test must FAIL, and for the right reason: an assertion,
  NotImplementedError from a stub, or the existing code doing the wrong thing (wrong value,
  wrong exception, no exception). Never an import, syntax or fixture error (except the
  interfaces-first case above). Fix any that fail for
  the wrong reason. If a test PASSES, stop: either the behavior already exists (say so and
  mark the test as characterization) or the test is broken (fix it).
- Commit the stubs and tests on their own:
  git commit -m "test(<scope>): acceptance tests"
- Do not dispatch subagents. Do not implement anything.

Report (under 15 lines): status (DONE | NEEDS_CONTEXT | BLOCKED), the commit SHA, each
test name with its failure reason, any brief ambiguity you resolved and how, and any
expected value you could not source (do not invent one: report NEEDS_CONTEXT).
```
