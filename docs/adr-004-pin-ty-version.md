# ADR-004: Pin the ty typechecker version

## Status

Accepted.

## Context

Both the parent repository and generated projects typecheck with `ty`. The
parent Makefile ran it through an unpinned `uvx` invocation, and the templated
dev dependency group declared `"ty"` without a version, so every install
resolved the latest release.

`ty` is pre-1.0 and its diagnostics change between releases. When ty 0.0.56
landed, estate repositories with unpinned installations broke without any code
change: the falcon-correlate and polythene main branches were red for days.
An unpinned typechecker makes gate outcomes depend on release timing rather
than on the code under review.

## Decision

Pin `ty` to an exact version everywhere it is installed:

- the parent Makefile's `typecheck` target runs `uvx … ty@0.0.56 check`;
- the templated dev dependency group declares `"ty==0.0.56"`, which pins the
  generated `uv run ty` invocations;
- contract tests assert the pinned forms so drift fails the suite.

Version bumps are deliberate: update the pin, fix any new diagnostics it
surfaces, and land both in a single pull request. Update the parent Makefile,
the templated dev group, and the contract assertions together, and re-render
both template toggle states before merging.

## Consequences

- Gate results are reproducible: a new ty release cannot break `main` in the
  parent repository or in generated projects.
- New ty diagnostics arrive only when a maintainer chooses to take them,
  alongside the fixes they require.
- The pin must be maintained by hand; generated projects inherit whatever
  version the template pinned at render time and manage their own bumps
  thereafter.
