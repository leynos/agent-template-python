"""Exercise wheel shell arguments and selected Python versions without Docker.

Parsed contracts cover the action's optional upload boundary. A stub uv records
the arguments passed by its real build script, while rendered workflow cases
follow nondefault baselines through reusable workflow and local action inputs.
Run these checks with ``pytest tests/test_workflow_boundaries.py``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    read_generated_text,
    require_mapping,
    require_sequence,
)
from tests.helpers.rendering import render_project
from tests.helpers.wheel_contracts import _assert_pure_wheel_action_contracts

_TEMPLATE_ACTION = (
    Path(__file__).resolve().parents[1]
    / "template/.github/actions/pure-python-wheel/action.yml"
)


def _action_steps(action: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the steps in a parsed composite action.

    Parameters
    ----------
    action
        Parsed composite action containing its runs mapping.

    Returns
    -------
    list[dict[str, Any]]
        Action steps in execution order.
    """
    return require_sequence(require_mapping(action, "runs", "action"), "steps", "runs")


def _job_steps(workflow: dict[str, Any], job_name: str) -> list[dict[str, Any]]:
    """Return a named job's parsed steps.

    Parameters
    ----------
    workflow
        Parsed workflow containing its jobs mapping.
    job_name
        Job whose steps are required.

    Returns
    -------
    list[dict[str, Any]]
        Job steps in execution order.
    """
    jobs = require_mapping(workflow, "jobs", "workflow")
    job = require_mapping(jobs, job_name, "workflow jobs")
    return require_sequence(job, "steps", job_name)


def _step_using(steps: list[dict[str, Any]], action: str) -> dict[str, Any]:
    """Return the unique step referencing an action, independently of its ref.

    Parameters
    ----------
    steps
        Parsed job or composite-action steps.
    action
        Expected action path without a ref.

    Returns
    -------
    dict[str, Any]
        The uniquely matching action step.
    """
    matching = [
        step for step in steps if str(step.get("uses", "")).split("@")[0] == action
    ]
    assert len(matching) == 1, f"Expected one step using {action}"
    return matching[0]


def _read_workflow(project: Path, name: str) -> dict[str, Any]:
    """Read a generated workflow with assertion-focused diagnostics.

    Parameters
    ----------
    project
        Generated project root.
    name
        Workflow filename beneath .github/workflows.

    Returns
    -------
    dict[str, Any]
        Parsed workflow mapping.
    """
    return parse_yaml_mapping(
        read_generated_text(project / ".github/workflows" / name), name
    )


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        ("remove-upload", "mapping key 'upload-artefact'"),
        ("boolean-default", "default to string true"),
        ("required-upload", "remain optional"),
        ("remove-condition", "explicit true input"),
        ("unguarded-upload", "explicit true input"),
        ("remove-upload-action", "use the upload-artifact action"),
        ("wrong-upload-action", "use the upload-artifact action"),
        ("remove-output-env", "through OUT_DIR"),
        ("unquoted-output", "one argument"),
        ("wrong-upload-path", "selected output directory"),
    ],
)
def test_pure_wheel_contract_rejects_broken_upload_boundaries(
    mutation: str, diagnostic: str
) -> None:
    """Reject representative removals and miswirings of the upload boundary."""
    action = parse_yaml_mapping(
        read_generated_text(_TEMPLATE_ACTION), "pure wheel action"
    )
    inputs = require_mapping(action, "inputs", "pure wheel action")
    steps = _action_steps(action)
    build = next(step for step in steps if step.get("name") == "Build wheel")
    upload = next(step for step in steps if step.get("name") == "Upload wheel artefact")
    if mutation == "remove-upload":
        inputs.pop("upload-artefact")
    elif mutation == "boolean-default":
        inputs["upload-artefact"]["default"] = True
    elif mutation == "required-upload":
        inputs["upload-artefact"]["required"] = True
    elif mutation == "remove-condition":
        upload.pop("if")
    elif mutation == "unguarded-upload":
        upload["if"] = "always()"
    elif mutation == "remove-upload-action":
        upload.pop("uses")
    elif mutation == "wrong-upload-action":
        upload["uses"] = "actions/download-artifact@v4"
    elif mutation == "remove-output-env":
        build["env"].pop("OUT_DIR")
    elif mutation == "unquoted-output":
        build["run"] = build["run"].replace('"$OUT_DIR"', "$OUT_DIR")
    else:
        upload["with"]["path"] = "dist/*.whl"
    with pytest.raises((AssertionError, pytest.fail.Exception), match=diagnostic):
        _assert_pure_wheel_action_contracts(action)


def test_pure_wheel_build_preserves_spaced_output_directory(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Run the generated Bash script and observe one output-directory argument."""
    project = render_project(
        tmp_path / "wheel-arguments",
        copier,
        project_name="WheelArguments",
        package_name="wheel_arguments",
        use_rust=False,
    )
    action = parse_yaml_mapping(
        read_generated_text(
            project.path / ".github/actions/pure-python-wheel/action.yml"
        ),
        "generated pure wheel action",
    )
    _assert_pure_wheel_action_contracts(action)
    build = next(
        step for step in _action_steps(action) if step.get("name") == "Build wheel"
    )
    bash = shutil.which("bash")
    assert bash is not None, "The wheel composite action requires Bash"
    tools = tmp_path / "bin"
    tools.mkdir()
    uv = tools / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['ARGV_LOG']).write_text(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    output_directory = str(tmp_path / "wheel artefacts")
    log = tmp_path / "arguments.json"
    environment = os.environ.copy()
    environment.update(
        PATH=str(tools) + os.pathsep + environment.get("PATH", ""),
        OUT_DIR=output_directory,
        ARGV_LOG=str(log),
    )
    result = subprocess.run(
        [bash, "-eu", "-c", build["run"]],
        cwd=project.path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(log.read_text(encoding="utf-8")) == [
        "build",
        "--wheel",
        "--out-dir",
        output_directory,
    ], "The wheel build must preserve the selected directory as one uv argument"


@pytest.mark.parametrize("python_version", ["3.13", "3.14"])
@pytest.mark.parametrize("use_rust", [False, True], ids=["pure-python", "rust"])
def test_nondefault_python_baseline_reaches_downstream_workflows(
    copier: CopierFixture, tmp_path: Path, python_version: str, use_rust: bool
) -> None:
    """Follow a selected baseline through audit, coverage, and release inputs."""
    project = render_project(
        tmp_path / "workflow-baseline",
        copier,
        project_name="WorkflowBaseline",
        package_name="workflow_baseline",
        python_version=python_version,
        use_rust=use_rust,
    )
    for filename, job in (
        ("audit.yml", "audit"),
        ("coverage-main.yml", "coverage-upload"),
    ):
        setup = _step_using(
            _job_steps(_read_workflow(project.path, filename), job),
            "actions/setup-python",
        )
        assert re.fullmatch(r"actions/setup-python@[0-9a-fA-F]{40}", setup["uses"]), (
            f"{filename} should pin setup-python to a full commit SHA"
        )
        assert (
            require_mapping(setup, "with", filename).get("python-version")
            == python_version
        ), f"{filename} should use the selected Python baseline"

    release = _read_workflow(project.path, "release.yml")
    jobs = require_mapping(release, "jobs", "release workflow")
    if use_rust:
        caller = require_mapping(jobs, "build-wheels", "release workflow jobs")
        assert caller.get("uses") == "./.github/workflows/build-wheels.yml", (
            "Rust releases should call the local wheel workflow"
        )
        called = _read_workflow(project.path, "build-wheels.yml")
        triggers = called.get("on", called.get(True))
        assert isinstance(triggers, dict), "The wheel workflow should declare triggers"
        call = require_mapping(triggers, "workflow_call", "wheel workflow triggers")
        version_input = require_mapping(
            require_mapping(call, "inputs", "workflow_call"),
            "python-version",
            "wheel workflow inputs",
        )
        assert (
            version_input.get("required") is True
            and version_input.get("type") == "string"
        ), "The reusable wheel workflow should require a Python version string"
        wheel_step = _step_using(
            _job_steps(called, "build"), "./.github/actions/build-wheels"
        )
        assert (
            require_mapping(wheel_step, "with", "wheel workflow local action").get(
                "python-version"
            )
            == "${{ inputs['python-version'] }}"
        ), "The wheel workflow should forward its caller's Python version"
        action_name = "build-wheels"
    else:
        caller = _step_using(
            _job_steps(release, "pure-wheel"), "./.github/actions/pure-python-wheel"
        )
        action_name = "pure-python-wheel"
    assert (
        require_mapping(caller, "with", "release wheel caller").get("python-version")
        == python_version
    ), "Release wheel builds should receive the selected Python baseline"
    action = parse_yaml_mapping(
        read_generated_text(
            project.path / ".github/actions" / action_name / "action.yml"
        ),
        action_name,
    )
    inputs = require_mapping(action, "inputs", action_name)
    assert (
        require_mapping(inputs, "python-version", "wheel action inputs").get("required")
        is True
    ), "Wheel actions should require the caller's Python version"
    setup = _step_using(_action_steps(action), "actions/setup-python")
    assert (
        require_mapping(setup, "with", action_name).get("python-version")
        == "${{ inputs.python-version }}"
    ), "Wheel actions should forward the selected version to setup-python"
