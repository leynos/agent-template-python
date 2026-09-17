# ADR-006: Gate spelling with the shared typos-config-builder

## Status

Accepted. Supersedes
[ADR-003](adr-003-shared-oxford-spelling-base.md).

## Context

[ADR-003](adr-003-shared-oxford-spelling-base.md) kept generated projects on
the estate's en-GB-oxendict policy by vendoring a generator that refreshed a
cached copy of the shared dictionary, merged it with a local overlay, and
wrote a tracked `typos.toml` that continuous integration (CI) drift checked.
Both layers of this template carried that generator, a phrase-check helper,
a pinned `typos` version, and tests for all of them.

A 2026-09-14 estate sweep found fourteen independently maintained copies of
the phrase-check script and twenty-eight repositories whose pinned `typos`
version or generator revision had never been bumped since adoption. The
`typos-config-builder` project now packages that whole pipeline behind one
pinned `gate` command, and reads the shared dictionary in
`leynos/agent-helper-scripts` live rather than from a vendored snapshot.

## Decision

Both the template repository and every generated project run the shared
`typos-config-builder` gate as their only spelling quality gate, pinned to an
exact revision in a single Makefile variable.

One `gate` run refreshes the live shared dictionary into ignored
`.typos-oxendict-base.toml`, validated through `.typos-oxendict-base.json`,
merges it with the repository's `typos.local.toml` overlay, writes `typos.toml`
in place, runs the `typos` binary the builder pins over the selected tracked
files, and enforces the shared phrase corrections that `typos` cannot express.

The parent gates its own Markdown and its `*.md.jinja` sources with
`--scope all`, because its prose does not live in `*.md` files. Generated
projects gate tracked Markdown with the default scope.

Because the dictionary is live, `typos.toml` is a regenerated artefact rather
than a reviewed one. It is never drift checked, and generated projects ignore
it; the parent keeps its copy tracked only as a convenience snapshot.

## Consequences

- Generic Oxford stems stay curated once for the estate, and a word added
  there reaches every repository on its next run with no local change.
- Neither layer carries a generator, a phrase-check helper, a pinned `typos`
  version, or tests for any of them; one pinned builder revision replaces them.
- Product names, upstream quotations, and deliberate fixtures remain narrow
  local exceptions in `typos.local.toml`.
- Every run needs network access to the shared dictionary. The builder falls
  back to a valid cache, and then to its bundled snapshot, when the authority
  is unreachable, so an offline run reports a stale cache rather than failing.
- A shared-dictionary change can turn a previously passing repository red with
  no local commit. That is the accepted cost of one estate-wide policy, and the
  reason the configuration must never be drift checked.
