"""Black-box GitHub Actions validation through act."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture, CopierProject

EVENT = Path(__file__).parent / "fixtures" / "pull_request.event.json"
ACT_IMAGE = "ubuntu-latest=catthehacker/ubuntu:act-latest"


def docker_environment() -> dict[str, str]:
    """Return an environment that points act at a usable container socket."""
    env = os.environ.copy()
    user_podman_socket = Path(f"/run/user/{os.getuid()}/podman/podman.sock")
    if "DOCKER_HOST" not in env and user_podman_socket.exists():
        env["DOCKER_HOST"] = f"unix://{user_podman_socket}"
    return env


def prepare_git_repository(project: CopierProject) -> None:
    """Initialise the rendered project as a git repository for act."""
    commands = [
        ["git", "init"],
        ["git", "config", "user.email", "act@example.invalid"],
        ["git", "config", "user.name", "Act Validation"],
        ["git", "add", "."],
        ["git", "commit", "-m", "Initial template render"],
    ]
    for command in commands:
        subprocess.run(command, cwd=project.path, check=True, capture_output=True)


def run_act(project: CopierProject, *, artifact_dir: Path) -> tuple[int, str]:
    """Run the generated CI workflow through act and return its logs."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    env = docker_environment()
    command = [
        "act",
        "pull_request",
        "-j",
        "lint-test",
        "-e",
        str(EVENT),
        "-P",
        ACT_IMAGE,
        "--artifact-server-path",
        str(artifact_dir),
        "--json",
        "-b",
        "--container-daemon-socket",
        env.get("DOCKER_HOST", ""),
    ]
    completed = subprocess.run(
        command,
        cwd=project.path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=1200,
    )
    return completed.returncode, f"{completed.stdout}\n{completed.stderr}"


def require_act() -> None:
    """Skip local workflow validation when act or containers are unavailable."""
    if os.environ.get("RUN_ACT_VALIDATION") != "1":
        pytest.skip("set RUN_ACT_VALIDATION=1 to run act workflow validation")
    if shutil.which("act") is None:
        pytest.skip("act is not installed")
    if shutil.which("docker") is None:
        pytest.skip("docker-compatible container runtime is not installed")
    env = docker_environment()
    docker = subprocess.run(
        ["docker", "info"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if docker.returncode != 0:
        pytest.skip(f"docker-compatible runtime is unavailable:\n{docker.stderr}")


def assert_ci_exercised_expected_steps(logs: str, *, use_rust: bool) -> None:
    """Assert the workflow reached the expected Python and Rust test steps."""
    saw_coverage = False
    saw_python = False
    saw_rust = not use_rust
    for line in logs.splitlines():
        if not line.lstrip().startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        output = (
            event.get("Output")
            or event.get("output")
            or event.get("message")
            or event.get("msg")
            or ""
        )
        step = event.get("Step") or event.get("step") or ""
        saw_coverage = saw_coverage or "Test and Measure Coverage" in step
        saw_python = saw_python or "pytest" in output or "run_python.py" in output
        saw_rust = saw_rust or "cargo" in output or "run_rust.py" in output

    assert saw_coverage, f"coverage action step was not observed:\n{logs}"
    assert saw_python, f"Python tests were not observed:\n{logs}"
    assert saw_rust, f"Rust tests were not observed:\n{logs}"


def assert_act_result(project: CopierProject, code: int, logs: str, *, use_rust: bool) -> None:
    """Assert the workflow passed, allowing only a known act composite-output bug."""
    assert (project / "coverage.xml").exists()
    assert_ci_exercised_expected_steps(logs, use_rust=use_rust)
    if code == 0:
        return
    if (
        "Parameter INPUT_ARTEFACT_NAME_SUFFIX specified multiple times" in logs
        and "Provided artifact name input during validation is empty" in logs
    ):
        pytest.xfail(
            "act currently fails in the shared generate-coverage composite "
            "action output/archive phase after tests and coverage succeed"
        )
    assert code == 0, logs


@pytest.mark.act
def test_python_only_workflow_runs_with_shared_coverage_action(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Validate the Python-only generated CI workflow through act."""
    require_act()
    project = copier.copy(
        tmp_path / "act-pure",
        project_name="ActPure",
        package_name="act_pure",
        use_rust=False,
    )
    prepare_git_repository(project)

    code, logs = run_act(project, artifact_dir=tmp_path / "pure-artifacts")

    assert "leynos/shared-actions/.github/actions/generate-coverage" in (
        project / ".github" / "workflows" / "ci.yml"
    ).read_text()
    assert_act_result(project, code, logs, use_rust=False)


@pytest.mark.act
def test_rust_extension_workflow_runs_with_shared_coverage_action(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Validate the Rust-extension generated CI workflow through act."""
    require_act()
    project = copier.copy(
        tmp_path / "act-rust",
        project_name="ActRust",
        package_name="act_rust",
        use_rust=True,
    )
    prepare_git_repository(project)

    code, logs = run_act(project, artifact_dir=tmp_path / "rust-artifacts")

    workflow = (project / ".github" / "workflows" / "ci.yml").read_text()
    assert "leynos/shared-actions/.github/actions/generate-coverage" in workflow
    assert "cargo-manifest: rust_extension/Cargo.toml" in workflow
    assert_act_result(project, code, logs, use_rust=True)
