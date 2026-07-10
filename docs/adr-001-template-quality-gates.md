# ADR-001: Template Quality Gates

## Status

Accepted.

## Context

Generated projects must include one public local gate that is simple to run and
preserve independent clarity for Python and Rust tooling, and the template
should generate GitHub Actions workflows that closely match the local gate so
failures are predictable.

## Decision

Generated projects use `make all` as the public aggregate gate. The `lint`
target delegates to language-specific targets:

- `lint-python` runs Ruff, Interrogate (`--fail-under 100`), and Pylint through
  the PyPy-backed runner.
- `lint-rust` is rendered only when `use_rust` is enabled and runs rustdoc,
  Clippy, and Whitaker.
- `spelling` generates shared en-GB-oxendict policy and runs the pinned
  `typos` binary after the other aggregate prerequisites complete.

Tool revision pins are exposed as Makefile variables where the generated
Makefile owns installation or invocation. Generated Continuous Integration
workflows use shared actions for Rust setup and coverage so local and hosted
execution stay aligned.

## Consequences

The generated Makefile remains the primary developer interface, but individual
lint tiers can be run directly when narrowing failures. Rust-only tooling is not
rendered for Python-only projects. The repository tests assert key generated
file contracts instead of adding a snapshot framework to this branch.
