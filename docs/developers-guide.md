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
- `make lint` — runs Ruff lint checks and `interrogate --fail-under 100` against
  the `tests/` directory in the parent template test suite.
- `make typecheck` — runs `ty check` against the parent template test suite,
  supplying the test dependencies, including Hypothesis, through `uvx`. The
  `ty` version is pinned (`ty@0.0.56`) because unpinned installations broke
  estate repositories when ty 0.0.56 landed (falcon-correlate and polythene
  mains were red for days). Version bumps are deliberate: update the pin, fix
  any new diagnostics, and land both in one pull request (see ADR-004).
- `make test` — runs the template test suite via `uvx`, supplying
  Hypothesis, `pytest-copier`, `pyyaml`, `syrupy`, and `make-parser` without a
  manually managed virtual environment.
- `make spelling` — runs the shared `typos-config-builder` gate over every
  tracked file, so Markdown and the `*.md.jinja` template sources are both
  checked for en-GB-oxendict spelling.
- `make test WITH_ACT=1` — sets `RUN_ACT_VALIDATION=1` inside the pytest
  invocation, enabling the act-backed integration tests that run generated CI
  workflows locally. Requires `act` and Docker to be available.

`uvx` is required; the Makefile aborts with an error if it is not found on
`PATH`.

## Parent CI Workflows

The parent repository uses three separate GitHub Actions workflows to keep
Docker-dependent tests isolated from the standard template test gate:

- `.github/workflows/ci.yml` runs `make test`, `make check-fmt`, and
  `make spelling` on every push to `main` and on all pull requests. It installs
  `markdownlint-cli2`, `mbake`, and `mdtablefix` at pinned versions, lints
  Markdown through the pinned `DavidAnson/markdownlint-cli2-action`, and skips
  `make audit` for Dependabot pull requests with
  `if: github.actor != 'dependabot[bot]'`.
- `.github/workflows/audit.yml` runs `make audit` on a weekly schedule against
  the default branch.
- `.github/workflows/act-validation.yml` runs `make test WITH_ACT=1`. It
  additionally downloads the `act` binary at a pinned `ACT_VERSION`, verifies
  its SHA-256 checksum before extraction, and confirms Docker availability via
  `docker info`. The workflow exposes `ACT_GITHUB_TOKEN: ${{ github.token }}`
  only to the nested act test step so actions requiring `github.token` behave
  like they do on GitHub-hosted runners.

`act-validation` runs on `ubicloud-standard-4`. `runs-on` selects it with the
estate expression
`${{ github.event.pull_request.head.repo.fork &&
'ubuntu-latest' || 'ubicloud-standard-4' }}`.
A pull request from a fork cannot obtain an Ubicloud runner, so it falls back
to `ubuntu-latest`; a push has no pull request, so the fork value is null and
it selects Ubicloud. The larger class is for the disk: the nested act
containers filled a `standard-2` runner (`ENOSPC`), and on `standard-4` the act
step used about 10 GB of 83 GB free. An Ubicloud runner is a self-hosted
just-in-time runner, so GitHub's six-hour cap for hosted jobs does not bound
it; the job states its own `timeout-minutes: 45`, about twice its measured 21
minutes. `tests/test_parent_runner_placement.py` evaluates the expression for a
push, a same-repository pull request and a fork, rejects a literal label,
inverted arms, another label and another condition, and asserts an exact
inventory of the jobs that can land on Ubicloud with their ceilings.

## Makefile Template

`template/Makefile.jinja` defines the generated developer workflow. The default
`all` target runs build, formatting, linting, typechecking, tests, and
spelling. The spelling recipe runs last, so generated configuration cannot race
tests when callers enable parallel Make execution. Generated projects pin `ty`
in the dev dependency group (`ty==0.0.56`), so `make typecheck` resolves the
pinned typechecker; bumps follow the same deliberate policy as the parent
repository (ADR-004). The generated `audit` target is an explicit security gate
run by CI. It runs `pip-audit` for every rendered project and, when `use_rust`
is enabled, also runs `cargo audit` in the Rust extension crate.

Generated projects ship `docs/scripting-standards.md`
(`template/docs/scripting-standards.md` here), which sets the conventions for
automation scripts: `cuprum` for process execution, Cyclopts for command-line
interfaces, `pathlib` for paths, and `cmd-mox` for testing commands. Read it
before adding a script to the template or to a generated project.

The generated `lint` aggregate runs these targets:

- `lint-python` runs Ruff 0.16.8, `interrogate --fail-under 100` for 100%
  docstring coverage across `$(PYTHON_TARGETS)`, baseline Pylint, the DF12
  Python Lints v0.4.0 Pylint plugin, and Ambrleaks against `tests/`.
- `dead-code` runs Skylos against the repository and Vulture against test
  sources. `duplication` installs and runs the pinned Nose-based detector
  against the configured duplication families.
- `lint-actions` runs yamllint, Actionlint, action-validator, and shellcheck
  against workflows and local actions.
- `lint-rust` exists only when `use_rust` is enabled and runs rustdoc, Clippy,
  and Whitaker.
- `lint` runs the Python, dead-code, duplication, and Actions targets, plus
  `lint-rust` when `use_rust` is enabled.
- `audit` exists for both generated variants and runs `pip-audit`; Rust-enabled
  variants delegate to `rust-audit` for `cargo audit`.

`check-fmt` checks Ruff and mdtablefix formatting; the `fmt` target also sorts
imports. Rust-enabled projects additionally use `cargo fmt`. The Markdown gate
is `make markdownlint`, which runs markdownlint-cli2 and repository-wide
spelling. The default `make all` includes build, formatting, lint, typecheck,
tests, and spelling.

Tool revisions are exposed as Makefile variables such as `PYLINT_VERSION` and
`PYLINT_PYTHON`, so generated projects can override pins without editing target
recipes.

The generated Pylint tier runs the pinned `PYLINT_VERSION` through
`uv tool run --managed-python`. The project baseline must be at least 3.12;
`PYLINT_PYTHON` is `pypy@3.12` when the baseline is exactly 3.12 and CPython at
the selected baseline when it is higher. PyPy 8 parses Python 3.12, while no
managed PyPy parses Python 3.13 or later syntax. `syntax-error` stays enabled
in the generated policy, so a module the interpreter cannot parse fails the
lint. `tests/test_generated_pylint_tier.py` renders both shapes and runs the
rendered `$(PYLINT)` against the baseline's newest syntax and an unparsable
module.

## Continuous Integration Strategy

`template/.github/workflows/ci.yml.jinja` mirrors the generated local gates. It
sets up Python, Go, and Rust toolchains, then runs `make check-fmt`,
`make lint`, `make typecheck`, `make spelling`, and `make audit` except when
`github.actor == 'dependabot[bot]'`. It delegates coverage to
`leynos/shared-actions/.github/actions/generate-coverage`; Rust lint and test
tools are installed only when the Rust extension is enabled. The scheduled
`.github/workflows/audit.yml` workflow audits the default branch weekly as the
compensating control.

The parent workflows, generated CI, and Act-validation workflow provision Go
1.27 before invoking Actionlint 1.7.12, whose minimum is Go 1.25. They disable
Go module caching because the projects have no Go module, and add `GOPATH/bin`
to `GITHUB_PATH` after installation. Stable Rust/Cargo is provisioned for the
`mdtablefix` `cargo-binstall` installer in both pure-Python and Rust-enabled
projects. These workflow prerequisites do not change the selected
`python_version` application baseline. For Rust-enabled projects, the Rust lint
and test cache uses the `rust_extension -> target` workspace and retains the
cargo-nextest, cargo-audit, and Whitaker tool-cache directories; this
Rust-specific cache configuration and the Rust lint and test tools are only
included when the extension is enabled.

The shared coverage action runs Python coverage through xdist-backed SlipCover
support. Generated pytest discovery is therefore constrained to the top-level
`tests/` tree via `tool.pytest.ini_options.testpaths`; do not add pytest unit
tests under package module directories or `unittests/` subdirectories.

Generated CI and the `coverage-main` workflow use the shared
`generate-coverage` action to install cargo-nextest from an official release.
The installer verifies both the release archive and executable hashes. A
checksum mismatch fails before Rust tests or coverage run, so it cannot qualify
for the Act archive-phase exception. The output script receives the coverage
path and artefact suffix as explicit arguments, so Act's duplicate `INPUT_*`
spellings cannot collide during parameter binding.

`template/.github/workflows/act-validation.yml.jinja` keeps rendered workflow
validation separate from generated application CI. It installs `act`, verifies
Docker availability, and runs `make test WITH_ACT=1`.

Local Act runs disable only the shared coverage action's artefact publication,
because the pinned Act 0.2.84 server does not support that upload protocol.
Tests, coverage generation, output checks, the coverage ratchet, and valid
`coverage.xml` remain required; the run retains `act.log` and `coverage.xml`
under `ACT_EVIDENCE_DIR`. Publication stays enabled for generated workflow runs
on GitHub. The parent Act-validation job uploads both retained coverage reports
separately; download both reports and validate their XML before treating
artefact transport as verified.

Rust-enabled workflows pass `rust_extension/Cargo.toml` to the coverage action
because the generated Python project root does not contain a Rust manifest.

The mutation-testing workflow template is rendered when either mutation engine
is available. Its mutmut job requires a minimum Python version of 3.13 or
newer; the hidden `mutmut_supported` Copier answer enforces that gate. The
cargo-mutants job is gated independently by `use_rust`, so a Rust-enabled
project with a Python 3.12 baseline still receives Rust mutation testing. Both
jobs delegate to reusable `leynos/shared-actions` workflows. Dependabot owns
their pinned commit SHAs; contract tests and documentation must not duplicate
those values because Dependabot cannot update them outside the workflow
template.

### Workflow pins and Dependabot

Dependabot owns the upgrade of GitHub Actions and reusable workflows, including
calls into `leynos/shared-actions`. Contract tests that assert a caller's exact
commit SHA create a lockstep dependency: every time Dependabot opens a bump PR,
the test fails until a human edits the pinned constant to match. That defeats
the purpose of automated dependency updates and turns a routine bump into a
manual chore. [ADR-005](adr-005-assert-workflow-shape-not-shas.md) records this
decision.

Contract tests may still verify the *shape* of a reusable-workflow caller. They
must not verify the specific SHA value.

- Do assert the workflow references the correct reusable workflow path.
- Do assert the ref is pinned to a full 40-character commit SHA, not a
  mutable branch such as `main` or `rolling`.
- Do assert the expected `on:` triggers, least-privilege `permissions:`, and
  the inputs the caller relies on.
- Do not hard-code the current SHA value as an expected string. Match it with
  a pattern instead.
- Do not fail a test purely because Dependabot bumped the pinned SHA.

```python
import re

SHA_RE = re.compile(r"^[0-9a-f]{40}$")

def test_uses_pinned_full_sha(caller_step):
    ref = caller_step["uses"].split("@")[-1]
    assert SHA_RE.match(ref), f"expected a 40-hex commit SHA, got {ref!r}"
```

If a workflow's behaviour genuinely depends on a feature only present from a
particular commit onwards, express that as a comment or a changelog note, not
as a test assertion on the SHA string.

## Shared Spelling Configuration

[ADR-006](adr-006-shared-typos-config-builder-gate.md) records the shared
`typos-config-builder` gate, superseding the vendored generator of
[ADR-003](adr-003-shared-oxford-spelling-base.md). Both the parent and the
generated project keep `.typos-oxendict-base.toml` and
`.typos-oxendict-base.json` untracked. Generic Oxford stems belong in
`leynos/agent-helper-scripts`; repository-only accepted words, patterns, and
file exclusions belong in `typos.local.toml`.

`make spelling` regenerates `typos.toml` from the live shared dictionary and
the overlay on every run, so a word added to the shared dictionary reaches this
repository with no local change. Because the dictionary is live, `typos.toml`
must never be drift checked in continuous integration, and hand edits to it are
overwritten on the next run. The parent and generated projects both track
`typos.toml` and commit the regenerated file, so a rendered project shows it as
a new file after its first gate run.

## Rust Integration

When `use_rust` is enabled, the template renders a PyO3 extension under
`rust_extension/`. Python packaging is handled by maturin, and the generated
Python package imports the Rust-backed implementation.

The generated Rust lint tier uses Clippy and Whitaker. The local Makefile never
installs Whitaker; it fails with a clear error when the wrapper is missing, and
the developer installs it with `whitaker-installer`. Tests prefer
`cargo nextest run` when `cargo-nextest` is available and fall back to
`cargo test` otherwise.

## Test Strategy

The repository tests render Python-only and Rust-enabled projects with
`pytest-copier`, then run the generated public gates. Additional generated-file
assertions check important template contracts such as Makefile target
structure, Rust documentation output, maturin configuration, and cargo error
messaging.

The optional `act` tests run generated GitHub Actions workflows as black-box
integration checks. On a non-zero result, diagnostics report the return code
and first failed step, including its stage, identity, and nearby output; the
complete Act log remains available for diagnosis. Error-looking output alone,
such as a cache metadata warning, does not establish that a step failed. A
successful result requires coverage and Python-test evidence, Rust-test
evidence when the extension is enabled, and a valid `coverage.xml`. The known
shared archive-phase exception is accepted only after the relevant tests and
coverage have succeeded and `coverage.xml` is valid, so an earlier workflow
failure cannot qualify.

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
