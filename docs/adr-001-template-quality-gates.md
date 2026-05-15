# ADR-001: Template Quality Gates

## Status

Accepted.

## Context

Generated projects need one public local gate that is simple to run, while still
keeping Python and Rust tooling independently understandable. The template also
needs generated GitHub Actions workflows to match the local gate closely enough
that failures are predictable.

## Decision

Generated projects use `make all` as the public aggregate gate. The `lint`
target delegates to language-specific targets:

- `lint-python` runs Ruff and Pylint through the PyPy-backed runner.
- `lint-rust` is rendered only when `use_rust` is enabled and runs rustdoc,
  Clippy, and Whitaker.

Tool revision pins are exposed as Makefile variables where the generated
Makefile owns installation or invocation. Generated Continuous Integration
workflows use shared actions for Rust setup and coverage so local and hosted
execution stay aligned.

## Consequences

The generated Makefile remains the primary developer interface, but individual
lint tiers can be run directly when narrowing failures. Rust-only tooling is not
rendered for Python-only projects. The repository tests assert key generated
file contracts instead of adding a snapshot framework to this branch.
