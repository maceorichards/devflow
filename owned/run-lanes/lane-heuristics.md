# Lane heuristics

`to-tickets` uses these criteria to propose a lane for each ticket, with a one-line reason. The user approves or changes every lane. Edit this file to taste.

## Propose `rigor` when any of these hold

- **Correctness-critical logic:** numerical methods, solvers, integrators, fitting or statistics, unit handling, data integrity, anything where a subtly wrong answer looks plausible.
- **Tight coupling:** the ticket changes an interface or behavior that several other modules depend on.
- **Hard to test after the fact:** subtle behavior, edge-case-heavy, or failure modes no simple test exposes.
- **Expensive to undo:** schema or file-format changes, persisted data, public APIs.

## Propose `fast` otherwise

Typical examples: plumbing, I/O wrappers, CLI flags, plotting and figures, configuration, docs, glue between well-defined interfaces, and the interfaces-first stub ticket itself (unless the interfaces are subtle).

## Tie-breakers

- Unsure → `rigor` for core-model code, `fast` for everything else.
- A `fast` ticket that blocks several `rigor` tickets stays `fast`. The rigor tickets will review its output against their own plans.
