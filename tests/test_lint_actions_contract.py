"""Exercise generated Actions validation without Docker."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from pytest_copier.plugin import CopierFixture

from tests.helpers.rendering import render_project


def _write_fake_command(directory: Path, name: str, body: str) -> None:
    """Write one executable command stub into a temporary ``bin`` directory.

    Parameters
    ----------
    directory : pathlib.Path
        Temporary directory that holds the fake command.
    name : str
        Executable name to create.
    body : str
        Shell script body following the interpreter line.
    """
    command = directory / name
    command.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    command.chmod(0o755)


def _make_environment(
    tmp_path: Path, *, action_path: str, log_path: Path
) -> tuple[dict[str, str], Path]:
    """Create fake tools and an isolated environment for ``make lint-actions``.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest temporary directory for fake executables and home.
    action_path : str
        Relative local action path emitted by the fake ``find`` command.
    log_path : pathlib.Path
        File where fake validators record their arguments.

    Returns
    -------
    tuple[dict[str, str], pathlib.Path]
        Process environment and fake executable directory.
    """
    binary_directory = tmp_path / "bin"
    binary_directory.mkdir()
    _write_fake_command(
        binary_directory,
        "find",
        "printf '%s\\n' \"${FAKE_ACTION_PATH:?}\"\n",
    )
    _write_fake_command(
        binary_directory,
        "uv",
        'printf \'uv %s\\n\' "$*" >> "$FAKE_LOG"\n'
        'if [ "${1-}" = run ] && [ "${2-}" = --script ]; then\n'
        "  printf '%s\\n' 'name: generated-action' 'on: push' "
        "'jobs:' '  lint:' '    runs-on: ubuntu-latest' '    steps: []'\n"
        "fi\n",
    )
    _write_fake_command(
        binary_directory,
        "action-validator",
        'printf \'action-validator %s\\n\' "$*" >> "$FAKE_LOG"\n',
    )
    _write_fake_command(
        binary_directory,
        "actionlint",
        'printf \'actionlint %s\\n\' "$*" >> "$FAKE_LOG"\n',
    )
    _write_fake_command(binary_directory, "shellcheck", "exit 0\n")

    environment = os.environ.copy()
    environment["HOME"] = str(tmp_path / "home")
    environment["PATH"] = os.pathsep.join(
        (str(binary_directory), environment.get("PATH", ""))
    )
    environment["FAKE_ACTION_PATH"] = action_path
    environment["FAKE_LOG"] = str(log_path)
    Path(environment["HOME"]).mkdir()
    return environment, binary_directory


def _run_lint_actions(
    project: Path, environment: dict[str, str], *, uv_path: Path
) -> subprocess.CompletedProcess[str]:
    """Run the rendered ``lint-actions`` target without invoking build.

    Parameters
    ----------
    project : pathlib.Path
        Rendered project directory containing the Makefile.
    environment : dict[str, str]
        Isolated command environment with fake tools on ``PATH``.
    uv_path : pathlib.Path
        Fake ``uv`` executable to use for generated tooling commands.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Captured Make result.
    """
    make = shutil.which("make")
    assert make is not None, "Actions contract tests require make"
    return subprocess.run(
        [
            make,
            "--no-print-directory",
            "-o",
            "build",
            f"UV={uv_path}",
            "lint-actions",
        ],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_lint_actions_propagates_find_failure(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """A failed action discovery command fails the generated Make target."""
    project = render_project(
        tmp_path / "find-failure",
        copier,
        project_name="ActionFindFailure",
        package_name="action_find_failure",
    )
    environment, binary_directory = _make_environment(
        tmp_path,
        action_path="unused",
        log_path=tmp_path / "find-failure.log",
    )
    _write_fake_command(
        Path(environment["PATH"].split(os.pathsep, maxsplit=1)[0]),
        "find",
        "printf '%s\\n' 'synthetic find failure' >&2\nexit 42\n",
    )

    result = _run_lint_actions(
        project.path, environment, uv_path=binary_directory / "uv"
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, (
        "generated lint-actions accepted failed action discovery:\n" + output
    )
    assert "synthetic find failure" in output, (
        "expected failed action discovery diagnostic in Make output:\n" + output
    )


def test_lint_actions_keeps_action_validation_pipeline(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Successful discovery still runs the validator and projected workflow lint."""
    project = render_project(
        tmp_path / "action-validation",
        copier,
        project_name="ActionValidation",
        package_name="action_validation",
    )
    action_path = ".github/actions/pure-python-wheel/action.yml"
    log_path = tmp_path / "action-validation.log"
    environment, binary_directory = _make_environment(
        tmp_path,
        action_path=action_path,
        log_path=log_path,
    )

    result = _run_lint_actions(
        project.path, environment, uv_path=binary_directory / "uv"
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        "generated lint-actions rejected successful action validation:\n" + output
    )
    log = log_path.read_text(encoding="utf-8")
    assert f"action-validator {action_path}" in log, (
        "expected local action validator to receive the discovered action"
    )
    assert f"uv run --script scripts/action_workflow.py {action_path}" in log, (
        "expected action workflow projection to run for the discovered action"
    )
    assert f"actionlint -stdin-filename {action_path} -" in log, (
        "expected actionlint to check the projected workflow with its source name"
    )
