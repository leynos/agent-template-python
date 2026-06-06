# Developer Guide

This repository is a Copier template. Source files under `template/` are
rendered into generated projects, while tests under `tests/` render those
projects and run their public quality gates.

## Parent Repository Makefile

The root `Makefile` provides developer workflow targets for working on the
template itself.

- `make help` — lists all `##`-annotated targets.
- `make check-fmt` — runs Ruff formatting checks against the parent template
  test suite.
- `make lint` — runs Ruff lint checks against the parent template test suite.
- `make typecheck` — runs `ty check` against the parent template test suite,
  supplying the test dependencies through `uvx`.
- `make test` — runs the template test suite via `uvx`, supplying
  `pytest-copier`, `pyyaml`, `syrupy`, and `make-parser` without a manually
  managed virtual environment.
- `make test WITH_ACT=1` — sets `RUN_ACT_VALIDATION=1` inside the pytest
  invocation, enabling the act-backed integration tests that run generated CI
  workflows locally. Requires `act` and Docker to be available.

`uvx` is required; the Makefile aborts with an error if it is not found on
`PATH`.

## Parent CI Workflows

The parent repository uses two separate GitHub Actions workflows to keep
Docker-dependent tests isolated from the standard template test gate:

- `.github/workflows/ci.yml` runs `make test` on every push to `main` and on
  all pull requests. It installs `markdownlint-cli2` and `mbake` at pinned
  versions.
- `.github/workflows/act-validation.yml` runs `make test WITH_ACT=1`. It
  additionally downloads the `act` binary at a pinned `ACT_VERSION`, verifies
  its SHA-256 checksum before extraction, and confirms Docker availability via
  `docker info`. The workflow exposes `ACT_GITHUB_TOKEN: ${{ github.token }}`
  only to the nested act test step so actions requiring `github.token` behave
  like they do on GitHub-hosted runners.

## Makefile Template

`template/Makefile.jinja` defines the generated developer workflow. The default
`all` target runs build, formatting, linting, typechecking, and tests.
The generated `audit` target is an explicit security gate run by CI. It runs
`pip-audit` for every rendered project and, when `use_rust` is enabled, also
runs `cargo audit` in the Rust extension crate.

The generated lint targets are split by language:

- `lint-python` runs Ruff and Pylint via the pinned PyPy-backed runner.
- `lint-rust` exists only when `use_rust` is enabled and runs rustdoc, Clippy,
  and Whitaker.
- `lint` delegates to the applicable language-specific targets.
- `audit` exists for both generated variants and runs `pip-audit`; Rust-enabled
  variants delegate to `rust-audit` for `cargo audit`.

Tool revisions are exposed as Makefile variables such as
`PYLINT_PYPY_SHIM_REF` and `WHITAKER_INSTALLER_REV`, so generated projects can
override pins without editing target recipes.

## Continuous Integration Strategy

`template/.github/workflows/ci.yml.jinja` mirrors the generated local gates. It
sets up Python, optionally sets up Rust, runs `make check-fmt`, `make lint`,
`make typecheck`, and `make audit`, then delegates coverage to
`leynos/shared-actions/.github/actions/generate-coverage`.

The shared coverage action runs Python coverage through xdist-backed SlipCover
support. Generated pytest discovery is therefore constrained to the top-level
`tests/` tree via `tool.pytest.ini_options.testpaths`; do not add pytest unit
tests under package module directories or `unittests/` subdirectories.

`template/.github/workflows/act-validation.yml.jinja` keeps rendered workflow
validation separate from generated application CI. It installs `act`, verifies
Docker availability, and runs `make test WITH_ACT=1`.

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

### Test Helper Modules

Test helpers are organized under `tests/helpers/` into three modules, each with
a distinct responsibility:

**`tests/helpers/rendering.py`** — project rendering and command execution.

- `render_project` wraps the `pytest-copier` fixture to render a temporary
  project with explicit template answers.
- `run_quality_gates` runs the generated `make all` target via the rendered
  project wrapper.
- `check_generated_import` imports the generated package through `uv run` and
  asserts its `hello()` return value.
- `read_generated_file` reads a file from the rendered project root as UTF-8
  text, converting OS errors into `pytest.fail` exceptions.

**`tests/helpers/generated_files.py`** — file parsing with assertion-focused
error context.

- `read_generated_text` reads a `Path` and converts `OSError` into
  `pytest.fail`.
- `parse_toml_file` reads and parses a TOML file, converting decode errors
  into `pytest.fail`.
- `parse_yaml_mapping` parses a YAML string and asserts the result is a
  mapping.
- `require_mapping` / `require_sequence` extract nested keys from a parsed
  mapping, failing with a schema-path message when absent or the wrong type.

**`tests/helpers/tooling_contracts.py`** — generated tooling contract
assertions.

- `assert_common_make_targets` validates Makefile targets shared by all
  generated variants.
- `assert_generated_tooling_contracts` is the single entry-point that
  validates packaging configuration, AGENTS.md guidance, Makefile wiring, CI
  and release workflow structure, and wheel workflow/action contracts.
- `assert_ci_coverage_action_contract` validates the shared coverage action
  step and its inputs, including optional Rust cargo-manifest inputs.

All public helpers carry NumPy-style docstrings.  Internal helpers (prefixed
`_`) are private to the module and not part of the test API.
