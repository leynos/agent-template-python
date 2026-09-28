# ADR-001: Template Quality Gates

## Status

Accepted. Amended 2026-09-28; see the addendum on the Pylint runner.

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
- `spelling` runs the pinned `typos-config-builder` gate, which regenerates
  the shared en-GB-oxendict policy and runs Typos, after the other aggregate
  prerequisites complete.

Tool revision pins are exposed as Makefile variables where the generated
Makefile owns installation or invocation. Generated Continuous Integration
workflows use shared actions for Rust setup and coverage so local and hosted
execution stay aligned.

## Consequences

The generated Makefile remains the primary developer interface, but individual
lint tiers can be run directly when narrowing failures. Rust-only tooling is
not rendered for Python-only projects. The repository tests assert key
generated file contracts instead of adding a snapshot framework to this branch.

## Addendum (2026-09-28): plain Pylint on the baseline interpreter

The Pylint tier no longer runs through the PyPy-backed `pylint-pypy-shim`
runner. PyPy 8 implements Python 3.12, uv ships it as a managed interpreter,
and Pylint 4.0.9 runs on it without the shim's patch. Generated projects run a
pinned `pylint==$(PYLINT_VERSION)` through `uv tool run --managed-python`.
`PYLINT_PYTHON` follows the `python_version` answer: `pypy@3.12` for a 3.12 or
older baseline, and CPython at the baseline for anything newer, because no
managed PyPy parses Python 3.13 or later syntax. The generated Pylint policy no
longer disables `syntax-error`, so a module the interpreter cannot parse fails
the lint instead of being skipped. `tests/test_generated_pylint_tier.py`
renders both shapes and runs the rendered command end to end.
