"""Validate rendered CI and act-validation workflow contracts.

This module owns generated CI workflow assertions, including coverage-action
inputs, act-validation workflow structure, and shared checkout credential
checks.  Release workflow helpers import ``_checkout_steps_disable_credentials``
from here so checkout security behaviour is asserted consistently.
"""

from __future__ import annotations

import re
from typing import Any

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
)

# Dependabot owns the shared-actions commit SHA; contract tests assert the
# reusable action path and that it is pinned to a full 40-hex commit SHA, but
# not which SHA. See docs/developers-guide.md, "Workflow pins and Dependabot".
_GENERATE_COVERAGE_USES_RE = re.compile(
    r"^leynos/shared-actions/\.github/actions/generate-coverage@[0-9a-f]{40}$"
)
_UPLOAD_CODESCENE_COVERAGE_USES_RE = re.compile(
    r"^leynos/shared-actions/\.github/actions/upload-codescene-coverage@[0-9a-f]{40}$"
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
    coverage_uses = str(coverage_step.get("uses"))
    assert _GENERATE_COVERAGE_USES_RE.match(coverage_uses), (
        "expected CI to use the shared coverage action pinned to a 40-hex "
        f"commit SHA, got {coverage_uses!r}"
    )
    assert coverage_step.get("if") == "${{ github.event_name == 'pull_request' }}", (
        "expected CI coverage generation to be guarded to pull requests so "
        "coverage-main.yml owns the push-to-main upload"
    )
    coverage_inputs = require_mapping(coverage_step, "with", "coverage step")
    assert coverage_inputs.get("output-path") == "coverage.xml", (
        "expected CI coverage output path to match the act assertion"
    )
    assert coverage_inputs.get("format") == "cobertura", (
        "expected CI coverage format to match the CodeScene upload"
    )
    assert coverage_inputs.get("with-ratchet") == "true", (
        "expected CI coverage to advance the ratchet baseline"
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


def assert_coverage_main_workflow_contract(
    *, coverage_main_workflow: str, package_name: str, use_rust: bool
) -> None:
    """Assert the generated push-to-main coverage upload workflow contract.

    Parameters
    ----------
    coverage_main_workflow : str
        UTF-8 text of the generated ``coverage-main.yml`` workflow.
    package_name : str
        Generated Python import package name used to derive the coverage
        artefact suffix.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.

    Returns
    -------
    None
        The helper returns after the coverage-main workflow contract matches
        expectations.

    Raises
    ------
    AssertionError
        Raised when the triggers, guarded upload, coverage generation, or Rust
        manifest wiring are wrong.

    Examples
    --------
    Validate a rendered coverage-main workflow::

        assert_coverage_main_workflow_contract(
            coverage_main_workflow=coverage_main_workflow,
            package_name="example_pkg",
            use_rust=True,
        )
    """
    # ``on:`` is parsed by PyYAML as the boolean key ``True``, so assert the
    # triggers against the raw text to stay robust.
    assert "branches: [main]" in coverage_main_workflow, (
        "expected coverage-main to upload on push to main"
    )
    assert "workflow_dispatch:" in coverage_main_workflow, (
        "expected coverage-main to allow manual dispatch (automerge pushes do "
        "not fire push-event workflows)"
    )
    parsed = parse_yaml_mapping(coverage_main_workflow, "coverage-main workflow")
    jobs = require_mapping(parsed, "jobs", "coverage-main workflow")
    upload_job = require_mapping(jobs, "coverage-upload", "coverage-main jobs")
    permissions = require_mapping(upload_job, "permissions", "coverage-upload job")
    assert permissions.get("contents") == "read", (
        "expected coverage-main upload job to restrict GITHUB_TOKEN to reads"
    )
    steps = require_sequence(upload_job, "steps", "coverage-upload job")

    generate_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Generate coverage"
    ]
    assert len(generate_steps) == 1, "expected one shared coverage generation step"
    generate_step = generate_steps[0]
    generate_uses = str(generate_step.get("uses"))
    assert _GENERATE_COVERAGE_USES_RE.match(generate_uses), (
        "expected coverage-main to use the shared coverage action pinned to "
        f"a 40-hex commit SHA, got {generate_uses!r}"
    )
    generate_inputs = require_mapping(generate_step, "with", "coverage generation step")
    assert generate_inputs.get("output-path") == "coverage.xml", (
        "expected coverage-main to write cobertura coverage.xml"
    )
    assert generate_inputs.get("format") == "cobertura", (
        "expected coverage-main to generate cobertura coverage for CodeScene"
    )
    assert generate_inputs.get("with-ratchet") == "true", (
        "expected coverage-main to advance the authoritative ratchet baseline"
    )
    assert generate_inputs.get("artefact-name-suffix") == package_name.replace(
        "_", "-"
    ), "expected package-specific coverage artefact name suffix"

    upload_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("name") == "Upload coverage data to CodeScene"
    ]
    assert len(upload_steps) == 1, "expected one guarded CodeScene upload step"
    upload_step = upload_steps[0]
    upload_uses = str(upload_step.get("uses"))
    assert _UPLOAD_CODESCENE_COVERAGE_USES_RE.match(upload_uses), (
        "expected coverage-main to use the shared upload action pinned to a "
        f"40-hex commit SHA, got {upload_uses!r}"
    )
    assert upload_step.get("if") == "env.CS_ACCESS_TOKEN != ''", (
        "expected the CodeScene upload to skip when the access token is absent"
    )
    upload_inputs = require_mapping(upload_step, "with", "CodeScene upload step")
    assert upload_inputs.get("format") == "cobertura", (
        "expected the CodeScene upload to send cobertura coverage"
    )
    assert upload_inputs.get("path") == "coverage.xml", (
        "expected the CodeScene upload to read coverage.xml"
    )

    if use_rust:
        assert generate_inputs.get("cargo-manifest") == "rust_extension/Cargo.toml", (
            "expected Rust variant coverage-main to pass the extension manifest"
        )
        assert "leynos/shared-actions/.github/actions/setup-rust" in (
            coverage_main_workflow
        ), "expected Rust variant coverage-main to set up Rust"
    else:
        assert "cargo-manifest" not in coverage_main_workflow, (
            "expected pure-Python coverage-main to omit Rust coverage inputs"
        )
        assert "setup-rust" not in coverage_main_workflow, (
            "expected pure-Python coverage-main to omit Rust setup"
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
    assert "make spelling" in ci_workflow, (
        "expected generated CI workflow to run the spelling gate"
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
    assert "cs-coverage upload" not in ci_workflow, (
        "expected the pull-request CI job to defer the CodeScene upload to "
        "coverage-main.yml"
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
