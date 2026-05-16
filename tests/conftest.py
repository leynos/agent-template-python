"""Pytest-copier configuration for this template."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def copier_template_paths() -> list[str]:
    """Copy only template sources into pytest-copier's temporary repository."""
    return ["copier.yml", "template"]


def container_info_command() -> list[str] | None:
    """Return the available container runtime info command."""
    if shutil.which("docker") is not None:
        return ["docker", "info"]
    if shutil.which("podman") is not None:
        return ["podman", "info"]
    return None


def docker_environment() -> dict[str, str]:
    """Return an environment that points act at a usable container socket."""
    env = os.environ.copy()
    user_podman_socket = Path(f"/run/user/{os.getuid()}/podman/podman.sock")
    if "DOCKER_HOST" not in env and user_podman_socket.exists():
        env["DOCKER_HOST"] = f"unix://{user_podman_socket}"
    return env


@pytest.fixture
def act_ready() -> None:
    """Ensure local act workflow validation can run."""
    if os.environ.get("RUN_ACT_VALIDATION") != "1":
        pytest.skip("set RUN_ACT_VALIDATION=1 to run act workflow validation")
    if shutil.which("act") is None:
        pytest.skip("act is not installed")
    info_command = container_info_command()
    if info_command is None:
        pytest.skip("docker-compatible container runtime is not installed")
    runtime = subprocess.run(
        info_command,
        env=docker_environment(),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if runtime.returncode != 0:
        pytest.skip(f"docker-compatible runtime is unavailable:\n{runtime.stderr}")
