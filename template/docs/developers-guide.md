# Developer guide

This guide explains the contributor workflow for the generated project.

## Local workflow

Use `make all` as the public entrypoint for formatting, linting, typechecking,
and tests. Use narrower Make targets when investigating a specific failure, then
return to the aggregate gate before treating the change as complete.

## Automation scripts

Before adding or updating helper scripts, read
[Scripting standards](scripting-standards.md). New and updated scripts should
use `Cyclopts` for command-line interfaces, `cuprum` for typed and
catalogue-bound external command execution, `pathlib` for filesystem paths, and
`cmd-mox` when tests need to mock external executables.

Script changes should update the scripting guide when they introduce a new
convention, command catalogue, testing pattern, or operational expectation that
future contributors need to follow.

## GitHub Actions

The generated repository includes GitHub Actions workflows and local composite
actions under `.github/`.

- `.github/workflows/ci.yml` runs on pushes to `main` and on pull requests. It
  sets up Python 3.13, installs `uv`, validates the generated `Makefile` with
  `mbake`, runs `make build`, `make check-fmt`, `make lint`, and
  `make typecheck`, then delegates coverage generation to the shared coverage
  action. When the Rust extension is enabled, it also sets up Rust, installs
  Rust lint and test tools, and passes `rust_extension/Cargo.toml` to coverage.
- `.github/workflows/release.yml` publishes wheels when a `v*.*.*` tag is
  pushed. It builds a pure Python wheel, creates a GitHub release with generated
  release notes, downloads wheel artifacts, and uploads them to the tag release.
- `.github/workflows/build-wheels.yml` is a reusable workflow for extension
  builds. It accepts a Python version and builds wheels across Linux, Windows,
  and macOS architectures via `.github/actions/build-wheels`.
- `.github/workflows/get-codescene-sha.yml` is manually dispatched. It fetches
  the CodeScene coverage CLI installer, computes its SHA-256 digest, and writes
  the result to the `CODESCENE_CLI_SHA256` repository variable.
- `.github/actions/build-wheels` wraps `cibuildwheel` with `uvx` and uploads
  architecture-specific wheel artifacts.
- `.github/actions/pure-python-wheel` builds a pure Python wheel with
  `uv build --wheel` and uploads the resulting artifact.
- `.github/dependabot.yml` enables dependency update pull requests for GitHub
  Actions and Python packages. Rust-enabled projects also receive Cargo updates.

Configure `CS_ACCESS_TOKEN` when CodeScene coverage upload is required. Keep
`CODESCENE_CLI_SHA256` populated with the refresh workflow so CI can verify the
downloaded CodeScene installer before upload.
