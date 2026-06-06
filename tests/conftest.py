"""Configure shared pytest fixtures for template validation.

This module centralises fixtures and runtime probes used by the repository's
test suite.  It tells ``pytest-copier`` which template files to copy into its
temporary repository and gates local ``act`` workflow validation behind explicit
environment and container-runtime checks.

The fixtures are useful when testing generated project variants or when running
the generated GitHub Actions workflow locally.  The ``act_ready`` fixture skips
workflow validation unless ``RUN_ACT_VALIDATION=1`` is set and a Docker-
compatible runtime is reachable.

Examples
--------
Run template tests with the default fixture configuration::

    python -m pytest tests/test_template.py -v

Run act-backed workflow validation when local prerequisites are available::

    RUN_ACT_VALIDATION=1 python -m pytest -m act -v
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest

from tests.utilities import docker_environment

MINIMUM_ACT_VERSION = (0, 2, 84)
ACT_VERSION_PATTERN = re.compile(r"\bact version v?(\d+)\.(\d+)\.(\d+)\b")


@pytest.fixture(scope="session")
def copier_template_paths() -> list[str]:
    """Return template paths copied into pytest-copier repositories.

    The fixture limits each rendered test repository to the source files needed
    by Copier.  This keeps unrelated repository files out of generated projects
    and makes rendered output easier to reason about.

    Yields
    ------
    list[str]
        Repository-relative template paths copied by ``pytest-copier``.

    Scope
    -----
    session
        The path list is stable for the whole pytest session.

    Raises
    ------
    None
        This fixture performs no filesystem access.

    Examples
    --------
    ``pytest-copier`` consumes this fixture automatically while rendering::

        project = copier.copy(tmp_path / "project", use_rust=False)
    """
    return ["copier.yml", "template"]


def container_info_command() -> list[str] | None:
    """Return the preferred available container runtime probe.

    The probe is used as a lightweight binary-availability check before the
    act validation fixture tries concrete runtime commands.  Docker is preferred
    when installed, with Podman as the fallback.

    Parameters
    ----------
    None

    Returns
    -------
    list[str] | None
        ``["docker", "info"]`` when Docker is installed, ``["podman", "info"]``
        when only Podman is installed, or ``None`` when neither binary exists.

    Raises
    ------
    None
        Binary detection is performed through ``shutil.which`` only.

    Examples
    --------
    Check whether a Docker-compatible runtime binary is installed::

        if container_info_command() is None:
            pytest.skip("runtime unavailable")
    """
    if shutil.which("docker") is not None:
        return ["docker", "info"]
    if shutil.which("podman") is not None:
        return ["podman", "info"]
    return None


def _runtime_info_commands() -> list[list[str]]:
    """Return available container runtime info commands in preference order."""
    commands: list[list[str]] = []
    if container_info_command() is not None and shutil.which("docker") is not None:
        commands.append(["docker", "info"])
    if shutil.which("podman") is not None:
        commands.append(["podman", "info"])
    return commands


def _parse_act_version(output: str) -> tuple[int, int, int] | None:
    """Return the semantic act version from command output."""
    match = ACT_VERSION_PATTERN.search(output)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _installed_act_version() -> tuple[int, int, int]:
    """Return the installed act version or skip when it cannot be parsed."""
    try:
        version = subprocess.run(
            ["act", "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"could not determine act version: {exc}")
    parsed_version = _parse_act_version(version.stdout)
    if parsed_version is None:
        pytest.skip(
            "could not parse act version from 'act --version' output: "
            f"{version.stdout.strip() or version.stderr.strip()}"
        )
    return parsed_version


@pytest.fixture
def act_ready() -> None:
    """Skip act-backed tests unless local workflow validation can run.

    The fixture requires ``RUN_ACT_VALIDATION=1``, an installed ``act`` binary,
    and at least one reachable Docker-compatible runtime.  It tries available
    runtime probes in order and skips only after all attempts fail.

    Yields
    ------
    None
        The fixture yields no value; successful setup allows the test to run.

    Scope
    -----
    function
        Runtime availability is checked for each act-backed test invocation.

    Raises
    ------
    pytest.skip.Exception
        Raised when validation is disabled, ``act`` is missing, no compatible
        runtime binary is installed, or all runtime probes fail.

    Examples
    --------
    Use the fixture in an act-backed integration test::

        def test_workflow(act_ready: None) -> None:
            ...
    """
    if os.environ.get("RUN_ACT_VALIDATION") != "1":
        pytest.skip("set RUN_ACT_VALIDATION=1 to run act workflow validation")
    if shutil.which("act") is None:
        pytest.skip("act is not installed")
    act_version = _installed_act_version()
    if act_version < MINIMUM_ACT_VERSION:
        found_version = ".".join(str(part) for part in act_version)
        minimum_version = ".".join(str(part) for part in MINIMUM_ACT_VERSION)
        pytest.skip(
            f"act >= {minimum_version} is required for Node24 action runtime "
            f"support; found act version {found_version}"
        )
    info_commands = _runtime_info_commands()
    if not info_commands:
        pytest.skip("docker-compatible container runtime is not installed")
    errors: list[str] = []
    for info_command in info_commands:
        try:
            runtime = subprocess.run(
                info_command,
                env=docker_environment(),
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{info_command[0]} info failed: {exc}")
            continue
        if runtime.returncode == 0:
            return
        errors.append(f"{info_command[0]} info failed:\n{runtime.stderr}")
    pytest.skip("docker-compatible runtime is unavailable:\n" + "\n".join(errors))
