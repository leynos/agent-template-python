# ADR-003: Generate spelling policy from a shared base

## Status

Accepted.

## Context

Generated projects need the same en-GB-oxendict policy as the wider `leynos`
estate. The `typos` `en-gb` locale enforces British `-our` and `-yse` forms but
prefers plain-British `-ise` over Oxford `-ize`. Copying curated overrides into
each generated project would cause drift, while making every exception global
would hide repository-specific mistakes.

## Decision

Generated projects refresh the tracked shared dictionary published by
`leynos/agent-helper-scripts` into ignored `.typos-oxendict-base.toml`, using
`.typos-oxendict-base.json` for source identity and freshness validators. The
generator merges that base with tracked `typos.local.toml` and writes a
deterministic, tracked `typos.toml`.

The refresh validates data before atomic replacement, keeps a valid cache when
its authority is not newer, and supports explicit offline reuse. The generated
Makefile pins `typos`, exposes `make spelling`, includes spelling in `make all`,
and runs it through Continuous Integration (CI). The template repository uses
the same mechanism for its own Markdown and rendered Markdown sources.

## Consequences

- Generic Oxford stems are curated once for the estate.
- Generated projects retain reviewable, reproducible configuration and work
  offline after their cache is populated.
- Product names, upstream quotations, and deliberate fixtures remain narrow
  local exceptions.
- A fresh checkout needs network access to collect the shared base before its
  first spelling run.
