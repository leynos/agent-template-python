"""Black-box GitHub Actions validation through act."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture, CopierProject

from tests.utilities import container_daemon_socket, docker_environment

EVENT = Path(__file__).parent / "fixtures" / "pull_request.event.json"
ACT_IMAGE = "ubuntu-latest=catthehacker/ubuntu:act-latest"
GENERATE_COVERAGE_STEP = "Test and Measure Coverage"

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
    ]
    docker_host = container_daemon_socket(env)
    if docker_host is not None:
        command.extend(["--container-daemon-socket", docker_host])
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


def iter_json_log_events(logs: str) -> list[dict[str, object]]:
    """Return JSON events from an act log stream."""
    events: list[dict[str, object]] = []
    for line in logs.splitlines():
        if not line.lstrip().startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def event_text(event: dict[str, object], *keys: str) -> str:
    """Return the first non-empty event field as text."""
    for key in keys:
        value = event.get(key)
        if value:
            return str(value)
    return ""


def assert_ci_exercised_expected_steps(logs: str, *, use_rust: bool) -> None:
    """Assert the workflow reached the expected Python and Rust test steps."""
    saw_coverage = False
    saw_python = False
    saw_rust = not use_rust
    for event in iter_json_log_events(logs):
        output = str(
            event_text(event, "Output", "output", "message", "msg")
        )
        step = str(
            event_text(event, "name", "step_name", "Step", "step")
        )
        in_coverage_step = GENERATE_COVERAGE_STEP in step
        saw_coverage = saw_coverage or (
            in_coverage_step and ("coverage.xml" in output or "Current coverage" in output)
        )
        saw_python = saw_python or (
            in_coverage_step and ("run_python.py" in output or "pytest -v" in output)
        )
        saw_rust = saw_rust or (
            in_coverage_step
            and (
                "run_rust.py" in output
                or "cargo nextest" in output
                or "cargo llvm-cov" in output
            )
        )

    assert saw_coverage, f"coverage action step was not observed:\n{logs}"
    assert saw_python, f"Python tests were not observed:\n{logs}"
    assert saw_rust, f"Rust tests were not observed:\n{logs}"


def assert_act_result(project: CopierProject, code: int, logs: str, *, use_rust: bool) -> None:
    """Assert the workflow passed, allowing only a known act composite-output bug."""
    assert (
        project / "coverage.xml"
    ).exists(), "act workflow should write coverage.xml in the generated project"
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


@pytest.mark.parametrize(
    ("name", "package", "use_rust", "artifact_dir"),
    [
        ("ActPure", "act_pure", False, "pure-artifacts"),
        ("ActRust", "act_rust", True, "rust-artifacts"),
    ],
)
@pytest.mark.act
def test_generated_workflow_runs_with_shared_coverage_action(
    act_ready: None,
    copier: CopierFixture,
    tmp_path: Path,
    name: str,
    package: str,
    use_rust: bool,
    artifact_dir: str,
) -> None:
    """Validate the generated CI workflow through act."""
    project = copier.copy(
        tmp_path / package,
        project_name=name,
        package_name=package,
        use_rust=use_rust,
    )
    prepare_git_repository(project)

    code, logs = run_act(project, artifact_dir=tmp_path / artifact_dir)

    workflow = (project / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert (
        "leynos/shared-actions/.github/actions/generate-coverage" in workflow
    ), "Generated workflow should use the shared generate-coverage action"
    if use_rust:
        assert (
            "cargo-manifest: rust_extension/Cargo.toml" in workflow
        ), "Rust workflow should pass the Rust extension manifest to coverage"
    assert_act_result(project, code, logs, use_rust=use_rust)
