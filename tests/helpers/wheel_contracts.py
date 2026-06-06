"""Validate rendered wheel workflow and composite action contracts.

Wheel-building assertions are separated from release workflow checks so matrix
coverage, checkout hardening, and build-command contracts remain focused on the
workflow/action files that produce wheel artefacts.
"""

from __future__ import annotations

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
)


def _assert_wheel_workflow_contracts(
    *,
    build_wheels_workflow: str,
    build_wheels_action: str,
    pure_wheel_action: str,
) -> None:
    """Assert generated wheel workflow and action contracts."""
    parsed_build_wheels = parse_yaml_mapping(
        build_wheels_workflow,
        "build-wheels workflow",
    )
    build_jobs = require_mapping(parsed_build_wheels, "jobs", "build-wheels workflow")
    build_job = require_mapping(build_jobs, "build", "build-wheels workflow jobs")
    strategy = require_mapping(build_job, "strategy", "build-wheels build job")
    matrix = require_mapping(strategy, "matrix", "build-wheels strategy")
    includes = require_sequence(matrix, "include", "build-wheels matrix")
    assert len(includes) == 6, (
        "expected build-wheels workflow to cover Linux, Windows, and macOS"
    )
    assert "persist-credentials: false" in build_wheels_workflow, (
        "expected build-wheels workflow checkout to disable credentials"
    )
    assert "uvx --with 'cibuildwheel>=2.16.0,<4.0.0' cibuildwheel" in (
        build_wheels_action
    ), "expected Rust wheel action to build through cibuildwheel"
    assert "persist-credentials: false" in build_wheels_action, (
        "expected build-wheels action checkout to disable credentials"
    )
    assert "uv build --wheel" in pure_wheel_action, (
        "expected pure-wheel action to build through uv"
    )
    assert "persist-credentials: false" in pure_wheel_action, (
        "expected pure-wheel action checkout to disable credentials"
    )
