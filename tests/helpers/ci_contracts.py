"""Validate rendered CI and act-validation workflow contracts.

This module owns generated CI workflow assertions, including coverage-action
inputs, act-validation workflow structure, and shared checkout credential
checks.  Release workflow helpers import ``_checkout_steps_disable_credentials``
from here so checkout security behaviour is asserted consistently.
"""

from __future__ import annotations

from typing import Any

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
)


def assert_ci_coverage_action_contract(
    *, ci_workflow: str, package_name: str, use_rust: bool
) -> None:
    """Assert generated CI coverage inputs used by act validation.

    Parameters
    ----------
    ci_workflow : str
        UTF-8 text of the generated CI workflow.
    package_name : str
        Generated Python import package name used to derive the coverage
        artefact suffix.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.

    Returns
    -------
    None
        The helper returns after the coverage action contract matches
        expectations.

    Raises
    ------
    AssertionError
        Raised when checkout credentials, coverage action pinning, coverage
        output settings, artefact naming, or Rust manifest inputs are wrong.

    Examples
    --------
    Validate a rendered CI workflow's coverage step::

        assert_ci_coverage_action_contract(
            ci_workflow=ci_workflow,
            package_name="example_pkg",
            use_rust=True,
        )
    """
    parsed_ci_workflow = _parse_ci_workflow(ci_workflow)
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    lint_test = require_mapping(jobs, "lint-test", "CI workflow jobs")
    steps = require_sequence(lint_test, "steps", "CI lint-test job")
    assert _checkout_steps_disable_credentials(steps), (
        "expected CI checkout steps to disable credential persistence"
    )
    coverage_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Test and Measure Coverage"
    ]
    assert len(coverage_steps) == 1, "expected one shared coverage action step"
    coverage_step = coverage_steps[0]
    assert (
        coverage_step.get("uses")
        == "leynos/shared-actions/.github/actions/generate-coverage"
        "@455d9ed03477c0026da96c2541ca26569a74acac"
    ), "expected CI to use the pinned shared coverage action"
    coverage_inputs = require_mapping(coverage_step, "with", "coverage step")
    assert coverage_inputs.get("output-path") == "coverage.xml", (
        "expected CI coverage output path to match the act assertion"
    )
    assert coverage_inputs.get("format") == "cobertura", (
        "expected CI coverage format to match the CodeScene upload"
    )
    assert coverage_inputs.get("artefact-name-suffix") == package_name.replace(
        "_", "-"
    ), "expected package-specific coverage artefact name suffix"
    if use_rust:
        assert coverage_inputs.get("cargo-manifest") == "rust_extension/Cargo.toml", (
            "expected Rust variant to pass the extension manifest to coverage"
        )
    else:
        assert "cargo-manifest" not in coverage_inputs, (
            "expected pure-Python variant to omit Rust coverage inputs"
        )


def _expected_python_matrix_legs(python_version: str) -> list[dict[str, Any]]:
    """Build the expected CI matrix legs for a baseline Python version.

    Parameters
    ----------
    python_version : str
        Minimum supported Python version answer (for example ``"3.10"``).

    Returns
    -------
    list[dict[str, Any]]
        Stable legs from the baseline through 3.14, followed by the
        experimental 3.15 leg.
    """
    baseline_minor = int(python_version.split(".")[1])
    legs: list[dict[str, Any]] = [
        {
            "python-version": f"3.{minor}",
            "python-label": f"3.{minor}",
            "allow-prereleases": False,
            "experimental": False,
        }
        for minor in range(baseline_minor, 15)
    ]
    legs.append(
        {
            "python-version": "3.15",
            "python-label": "3.15a",
            "allow-prereleases": True,
            "experimental": True,
        }
    )
    return legs


def assert_ci_python_matrix_contract(
    *,
    ci_workflow: str,
    multi_python_tests: bool,
    use_rust: bool,
    python_version: str = "3.10",
) -> None:
    """Assert the generated CI Python version matrix contract.

    Parameters
    ----------
    ci_workflow : str
        UTF-8 text of the generated CI workflow.
    multi_python_tests : bool
        Whether the rendered variant enables the multi-version test matrix.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.
    python_version : str, default="3.10"
        Minimum supported Python version answer passed to Copier.

    Returns
    -------
    None
        The helper returns after the matrix contract matches expectations.

    Raises
    ------
    AssertionError
        Raised when the matrix job is unexpectedly present or absent, when
        matrix legs diverge from the derived version list, when the
        experimental lane gates merges, or when per-leg steps are wrong.

    Examples
    --------
    Validate a rendered matrix-enabled CI workflow::

        assert_ci_python_matrix_contract(
            ci_workflow=ci_workflow,
            multi_python_tests=True,
            use_rust=False,
            python_version="3.12",
        )
    """
    parsed_ci_workflow = _parse_ci_workflow(ci_workflow)
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    if not multi_python_tests:
        assert "typecheck-test" not in jobs, (
            "expected matrix-off CI workflow to omit the typecheck-test job"
        )
        return
    job = require_mapping(jobs, "typecheck-test", "CI workflow jobs")
    assert job.get("name") == (
        "Typecheck and test (Python ${{ matrix.python-label }})"
    ), "expected matrix legs to be named after their Python label"
    assert job.get("continue-on-error") == "${{ matrix.experimental }}", (
        "expected experimental matrix legs to avoid gating merges"
    )
    strategy = require_mapping(job, "strategy", "typecheck-test job")
    assert strategy.get("fail-fast") is False, (
        "expected matrix legs to run to completion independently"
    )
    matrix = require_mapping(strategy, "matrix", "typecheck-test strategy")
    legs = require_sequence(matrix, "include", "typecheck-test matrix")
    assert legs == _expected_python_matrix_legs(python_version), (
        "expected matrix legs from the baseline through 3.14 plus an "
        "experimental 3.15 leg"
    )
    _assert_python_matrix_steps(job, use_rust=use_rust)


def _assert_python_matrix_steps(job: dict[str, Any], *, use_rust: bool) -> None:
    """Assert the per-leg steps of the generated matrix job.

    Parameters
    ----------
    job : dict[str, Any]
        Parsed ``typecheck-test`` job mapping.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.
    """
    steps = require_sequence(job, "steps", "typecheck-test job")
    assert _checkout_steps_disable_credentials(steps), (
        "expected matrix checkout steps to disable credential persistence"
    )
    step_names = [step.get("name") for step in steps if isinstance(step, dict)]
    for required in ("Set up Python", "Install code", "Run typechecker", "Run tests"):
        assert required in step_names, (
            f"expected matrix legs to include the {required!r} step"
        )
    setup_python = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Set up Python"
    )
    setup_python_inputs = require_mapping(setup_python, "with", "Set up Python step")
    assert setup_python_inputs.get("python-version") == (
        "${{ matrix.python-version }}"
    ), "expected matrix legs to install the leg's Python version"
    assert setup_python_inputs.get("allow-prereleases") == (
        "${{ matrix.allow-prereleases }}"
    ), "expected the experimental leg to allow prerelease interpreters"
    if use_rust:
        assert "Set up Rust" in step_names, (
            "expected Rust variant matrix legs to set up the Rust toolchain"
        )
    else:
        assert "Set up Rust" not in step_names, (
            "expected pure-Python matrix legs to omit Rust setup"
        )


def _parse_ci_workflow(ci_workflow: str) -> dict[str, Any]:
    """Parse a generated CI workflow as a YAML mapping."""
    return parse_yaml_mapping(ci_workflow, "CI workflow")


def _assert_ci_workflow_contracts(
    *, parsed_ci_workflow: dict[str, Any], ci_workflow: str, use_rust: bool
) -> None:
    """Assert generated CI workflow contracts.

    Parameters
    ----------
    parsed_ci_workflow : dict[str, Any]
        Parsed generated CI workflow mapping.
    ci_workflow : str
        UTF-8 text of the generated CI workflow, used for string-level contract
        assertions.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.
    """
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    lint_test = require_mapping(jobs, "lint-test", "CI workflow jobs")
    steps = require_sequence(lint_test, "steps", "CI lint-test job")
    assert _checkout_steps_disable_credentials(steps), (
        "expected generated CI workflow to disable checkout credentials"
    )
    assert "make check-fmt" in ci_workflow, (
        "expected generated CI workflow to run the formatting gate"
    )
    assert "make lint" in ci_workflow, (
        "expected generated CI workflow to run the lint gate"
    )
    assert "make typecheck" in ci_workflow, (
        "expected generated CI workflow to run the typecheck gate"
    )
    assert "make audit" in ci_workflow, (
        "expected generated CI workflow to run the dependency audit gate"
    )
    assert "make test WITH_ACT=1" not in ci_workflow, (
        "expected generated main CI workflow to leave act validation to a "
        "separate workflow"
    )
    assert "make build" in ci_workflow, (
        "expected generated CI workflow to build the project before checks"
    )
    assert "leynos/shared-actions/.github/actions/generate-coverage" in ci_workflow, (
        "expected generated CI workflow to use the shared coverage action"
    )
    if use_rust:
        assert "leynos/shared-actions/.github/actions/setup-rust" in ci_workflow, (
            "expected Rust variant CI to set up Rust"
        )
        rust_tool_steps = [
            step
            for step in steps
            if isinstance(step, dict)
            and step.get("name") == "Install Rust lint and test tools"
        ]
        assert len(rust_tool_steps) == 1, (
            "expected Rust variant CI to install Rust lint and test tools once"
        )
        rust_tool_env = require_mapping(
            rust_tool_steps[0],
            "env",
            "Install Rust lint and test tools step",
        )
        assert rust_tool_env.get("RUSTFLAGS") == "", (
            "expected Rust tool installation step to clear inherited RUSTFLAGS"
        )
        assert "Cache Rust lint and test tools" in ci_workflow, (
            "expected Rust variant CI to cache Rust tools"
        )
        assert "cargo-manifest: rust_extension/Cargo.toml" in ci_workflow, (
            "expected Rust variant CI to pass the Rust manifest to coverage"
        )
        assert "cargo install --locked cargo-audit" in ci_workflow, (
            "expected Rust variant CI to install cargo-audit"
        )
    else:
        assert "setup-rust" not in ci_workflow, (
            "expected pure-Python CI to omit Rust setup"
        )
        assert "cargo-manifest" not in ci_workflow, (
            "expected pure-Python CI to omit Rust coverage inputs"
        )
        assert "cargo-audit" not in ci_workflow, (
            "expected pure-Python CI to omit Rust audit installation"
        )


def _assert_act_validation_workflow_contracts(
    *, act_validation_workflow: str, use_rust: bool
) -> None:
    """Assert generated act-validation workflow contracts."""
    assert "name: Act Validation" in act_validation_workflow, (
        "expected generated act-validation workflow to be named"
    )
    assert "ACT_VERSION: v0.2.84" in act_validation_workflow, (
        "expected generated act-validation workflow to pin act"
    )
    assert "permissions:\n  contents: read" in act_validation_workflow, (
        "expected generated act-validation workflow to restrict GITHUB_TOKEN"
    )
    assert "MARKDOWNLINT_CLI2_VERSION: 0.22.1" in act_validation_workflow, (
        "expected generated act-validation workflow to pin markdownlint-cli2"
    )
    assert "MBAKE_VERSION: 1.4.6" in act_validation_workflow, (
        "expected generated act-validation workflow to pin mbake"
    )
    assert "act_Linux_x86_64.tar.gz" in act_validation_workflow, (
        "expected generated act-validation workflow to install act"
    )
    assert "${ACT_VERSION}/${act_archive}" in act_validation_workflow, (
        "expected generated act-validation workflow to build the act URL from ACT_VERSION"
    )
    assert "sha256sum -c -" in act_validation_workflow, (
        "expected generated act-validation workflow to verify the act archive checksum"
    )
    assert 'npm install -g "markdownlint-cli2@${MARKDOWNLINT_CLI2_VERSION}"' in (
        act_validation_workflow
    ), "expected generated act-validation workflow to install pinned markdownlint-cli2"
    assert 'uv tool install "mbake==${MBAKE_VERSION}"' in act_validation_workflow, (
        "expected generated act-validation workflow to install pinned mbake"
    )
    assert "docker info" in act_validation_workflow, (
        "expected generated act-validation workflow to verify Docker"
    )
    assert "make test WITH_ACT=1" in act_validation_workflow, (
        "expected generated act-validation workflow to run act-enabled tests"
    )
    if use_rust:
        assert "leynos/shared-actions/.github/actions/setup-rust" in (
            act_validation_workflow
        ), "expected Rust variant act-validation workflow to set up Rust"
    else:
        assert "setup-rust" not in act_validation_workflow, (
            "expected pure-Python act-validation workflow to omit Rust setup"
        )


def _checkout_steps_disable_credentials(steps: list[Any]) -> bool:
    """Return whether all checkout steps disable credential persistence."""
    checkout_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    return bool(checkout_steps) and all(
        isinstance(step.get("with"), dict)
        and step["with"].get("persist-credentials") is False
        for step in checkout_steps
    )
