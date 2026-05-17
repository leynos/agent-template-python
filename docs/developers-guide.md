# Developer Guide

This repository is a Copier template. Source files under `template/` are
rendered into generated projects, while tests under `tests/` render those
projects and run their public quality gates.

## Makefile Template

`template/Makefile.jinja` defines the generated developer workflow. The default
`all` target runs build, formatting, linting, typechecking, and tests.

The generated lint targets are split by language:

- `lint-python` runs Ruff and Pylint via the pinned PyPy-backed runner.
- `lint-rust` exists only when `use_rust` is enabled and runs rustdoc, Clippy,
  and Whitaker.
- `lint` delegates to the applicable language-specific targets.

Tool revisions are exposed as Makefile variables such as
`PYLINT_PYPY_SHIM_REF` and `WHITAKER_INSTALLER_REV`, so generated projects can
override pins without editing target recipes.

## Continuous Integration Strategy

`template/.github/workflows/ci.yml.jinja` mirrors the generated local gates. It
sets up Python, optionally sets up Rust, runs `make check-fmt`, `make lint`,
and `make typecheck`, then delegates coverage to
`leynos/shared-actions/.github/actions/generate-coverage`.

Rust-enabled workflows pass `rust_extension/Cargo.toml` to the coverage action
because the generated Python project root does not contain a Rust manifest.

## Rust Integration

When `use_rust` is enabled, the template renders a PyO3 extension under
`rust_extension/`. Python packaging is handled by maturin, and the generated
Python package imports the Rust-backed implementation.

The generated Rust lint tier uses Clippy and Whitaker. The local Makefile
installs Whitaker on demand when it is missing. Tests prefer `cargo nextest run`
when `cargo-nextest` is available and fall back to `cargo test` otherwise.

## Test Strategy

The repository tests render Python-only and Rust-enabled projects with
`pytest-copier`, then run the generated public gates. Additional generated-file
assertions check important template contracts such as Makefile target structure,
Rust documentation output, maturin configuration, and cargo error messaging.

The optional `act` tests run generated GitHub Actions workflows as black-box
integration checks. Their parser separates structured-log handling from the
domain assertions so workflow format details stay local to the adapter helpers.
