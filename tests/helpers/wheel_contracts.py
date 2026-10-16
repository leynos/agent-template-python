"""Validate rendered wheel workflow and composite action contracts.

Wheel-building assertions are separated from release workflow checks so matrix
coverage, checkout hardening, and build-command contracts remain focused on the
workflow/action files that produce wheel artefacts.
"""

from __future__ import annotations

import re
from typing import Any

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
)


def _assert_pure_wheel_action_contracts(action: dict[str, Any]) -> None:
    """Assert the pure wheel action's optional upload and output-directory wiring.

    Parameters
    ----------
    action
        Parsed pure Python wheel composite action.

    Returns
    -------
    None
        The helper returns after all upload-boundary assertions pass.

    Raises
    ------
    AssertionError
        Raised when the upload guard or output-directory boundary changes.
    pytest.fail.Exception
        Raised when a required action mapping or step sequence is missing.
    """
    inputs = require_mapping(action, "inputs", "pure wheel action")
    upload = require_mapping(inputs, "upload-artefact", "pure wheel inputs")
    assert upload.get("required") is False, "wheel upload should remain optional"
    assert upload.get("default") == "true", "wheel upload should default to string true"
    runs = require_mapping(action, "runs", "pure wheel action")
    steps = require_sequence(runs, "steps", "pure wheel action runs")
    builds = [step for step in steps if step.get("name") == "Build wheel"]
    uploads = [step for step in steps if step.get("name") == "Upload wheel artefact"]
    assert len(builds) == 1, "pure wheel action should contain one build step"
    assert len(uploads) == 1, "pure wheel action should contain one upload step"
    build, upload_step = builds[0], uploads[0]
    environment = require_mapping(build, "env", "pure wheel build step")
    assert environment.get("OUT_DIR") == "${{ inputs.out-dir }}", (
        "wheel build should receive the output directory through OUT_DIR"
    )
    assert build.get("shell") == "bash", "wheel build should use Bash"
    assert build.get("run") == 'uv build --wheel --out-dir "$OUT_DIR"', (
        "wheel build should pass the quoted output directory as one argument"
    )
    assert upload_step.get("if") == "inputs.upload-artefact == 'true'", (
        "wheel upload should run only for the explicit true input"
    )
    assert re.fullmatch(
        r"actions/upload-artifact@[^\s@]+", str(upload_step.get("uses", ""))
    ), "wheel upload should use the upload-artifact action with a nonempty ref"
    upload_inputs = require_mapping(upload_step, "with", "pure wheel upload step")
    assert upload_inputs.get("path") == "${{ inputs.out-dir }}/*.whl", (
        "wheel upload should read wheels from the selected output directory"
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
    _assert_pure_wheel_action_contracts(
        parse_yaml_mapping(pure_wheel_action, "pure wheel action")
    )
