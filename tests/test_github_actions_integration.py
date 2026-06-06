"""Validate the generated GitHub Actions workflow through act.

This module renders template variants, initialises them as temporary Git
repositories, and runs the generated CI workflow locally with ``act``.  It is a
black-box integration check for the workflow contract: generated projects should
use the shared coverage action, exercise Python tests, and exercise Rust checks
when the Rust extension is enabled.

The tests are marked ``act`` and depend on the ``act_ready`` fixture from
``tests.conftest``.  They are skipped by default unless local workflow
validation is explicitly enabled and a Docker-compatible runtime is available.

Examples
--------
Run the act-backed workflow checks when local prerequisites are installed::

    RUN_ACT_VALIDATION=1 python -m pytest -m act -v

Run this module's collection without enabling act validation::

    python -m pytest tests/test_github_actions_integration.py -v
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pytest_copier.plugin import CopierFixture, CopierProject

from tests.utilities import container_daemon_socket, docker_environment

EVENT = Path(__file__).parent / "fixtures" / "pull_request.event.json"
ACT_IMAGE = "ubuntu-latest=catthehacker/ubuntu:act-latest"
GENERATE_COVERAGE_STEP = "Test and Measure Coverage"


def prepare_git_repository(project: CopierProject) -> None:
    """Initialise a rendered project as a Git repository for act.

    Parameters
    ----------
    project
        Rendered ``pytest-copier`` project that should be committed before act
        runs the pull-request workflow.

    Returns
    -------
    None
        The helper returns after creating the initial commit.

    Raises
    ------
    subprocess.CalledProcessError
        Raised if any Git setup command fails.

    Examples
    --------
    Prepare a generated project before calling ``run_act``::

        prepare_git_repository(project)
    """
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
    """Run the generated CI workflow through act.

    Parameters
    ----------
    project
        Rendered project whose ``.github/workflows/ci.yml`` file should be
        executed.
    artifact_dir
        Directory where act should write workflow artifacts.

    Returns
    -------
    tuple[int, str]
        Process return code and combined standard output/error logs.

    Raises
    ------
    subprocess.TimeoutExpired
        Raised if act exceeds the configured subprocess timeout.

    Examples
    --------
    Run act for a prepared rendered project::

        code, logs = run_act(project, artifact_dir=tmp_path / "artifacts")
    """
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
    act_github_token = env.get("ACT_GITHUB_TOKEN")
    if act_github_token:
        command.extend(["-s", f"GITHUB_TOKEN={act_github_token}"])
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


@pytest.mark.parametrize(
    ("env", "expected_secret"),
    [
        ({}, None),
        ({"ACT_GITHUB_TOKEN": "nested-token"}, "GITHUB_TOKEN=nested-token"),
    ],
)
def test_run_act_forwards_only_explicit_act_github_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    env: dict[str, str],
    expected_secret: str | None,
) -> None:
    """Forward only explicit nested-act GitHub tokens.

    Parameters
    ----------
    monkeypatch
        Pytest fixture used to replace subprocess and environment helpers.
    tmp_path
        Temporary directory used as the fake rendered project and artifact
        location.
    env
        Sanitized act subprocess environment returned by ``docker_environment``.
    expected_secret
        Expected ``GITHUB_TOKEN`` secret argument, or ``None`` when no secret
        should be passed to act.

    Returns
    -------
    None
        The test passes when ``run_act`` forwards ``ACT_GITHUB_TOKEN`` as an act
        secret and does not synthesize a secret when it is absent.
    """
    captured_command: list[str] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        return subprocess.CompletedProcess(command, 0, "stdout", "stderr")

    monkeypatch.setattr(
        "tests.test_github_actions_integration.docker_environment",
        lambda: env,
    )
    monkeypatch.setattr(
        "tests.test_github_actions_integration.container_daemon_socket",
        lambda _: None,
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    project = cast("CopierProject", SimpleNamespace(path=tmp_path))

    run_act(project, artifact_dir=tmp_path / "artifacts")

    if expected_secret is None:
        assert "-s" not in captured_command, (
            "expected run_act not to pass act secrets without ACT_GITHUB_TOKEN"
        )
        assert not any(
            argument.startswith("GITHUB_TOKEN=") for argument in captured_command
        ), "expected run_act not to synthesize a GITHUB_TOKEN secret"
    else:
        assert "-s" in captured_command, (
            "expected run_act to pass an act secret when ACT_GITHUB_TOKEN is set"
        )
        secret_index = captured_command.index("-s") + 1
        assert captured_command[secret_index] == expected_secret, (
            "expected run_act to forward ACT_GITHUB_TOKEN as GITHUB_TOKEN secret"
        )


def iter_json_log_events(logs: str) -> list[dict[str, object]]:
    """Return JSON event objects from an act log stream.

    Parameters
    ----------
    logs
        Combined act output containing JSON and non-JSON log lines.

    Returns
    -------
    list[dict[str, object]]
        Parsed JSON object lines.  Non-object JSON values and malformed lines
        are ignored.

    Raises
    ------
    None
        Malformed JSON lines are skipped.

    Examples
    --------
    Extract structured act events before checking step output::

        events = iter_json_log_events(logs)
    """
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
    """Return the first non-empty event field as text.

    Parameters
    ----------
    event
        Parsed act JSON event.
    *keys
        Candidate field names to inspect in order.

    Returns
    -------
    str
        String value for the first truthy field, or an empty string when none
        of the requested fields is present.

    Raises
    ------
    None
        Missing fields are treated as empty values.

    Examples
    --------
    Prefer explicit output fields while tolerating act schema differences::

        text = event_text(event, "Output", "output", "message")
    """
    for key in keys:
        value = event.get(key)
        if value:
            return str(value)
    return ""


def assert_ci_exercised_expected_steps(logs: str, *, use_rust: bool) -> None:
    """Assert that act logs include the expected test and coverage steps.

    Parameters
    ----------
    logs
        Combined act output from ``run_act``.
    use_rust
        Whether the rendered project should include Rust-extension workflow
        steps.

    Returns
    -------
    None
        The helper returns after all expected workflow observations are present.

    Raises
    ------
    AssertionError
        Raised when coverage, Python tests, or required Rust checks are missing
        from the act logs.

    Examples
    --------
    Verify the observed steps after an act run::

        assert_ci_exercised_expected_steps(logs, use_rust=True)
    """
    saw_coverage = False
    saw_python = False
    saw_rust = not use_rust
    for event in iter_json_log_events(logs):
        output = str(event_text(event, "Output", "output", "message", "msg"))
        step = str(event_text(event, "name", "step_name", "Step", "step"))
        in_coverage_step = GENERATE_COVERAGE_STEP in step
        saw_coverage = saw_coverage or (
            in_coverage_step
            and ("coverage.xml" in output or "Current coverage" in output)
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


def assert_act_result(
    project: CopierProject, code: int, logs: str, *, use_rust: bool
) -> None:
    """Assert the act workflow result for a rendered project.

    Parameters
    ----------
    project
        Rendered project whose workflow should have produced ``coverage.xml``.
    code
        Return code from the act subprocess.
    logs
        Combined act output from ``run_act``.
    use_rust
        Whether Rust workflow steps are expected in the logs.

    Returns
    -------
    None
        The helper returns when the workflow passed or xfails for the known act
        composite-output issue after required checks succeeded.

    Raises
    ------
    AssertionError
        Raised when required artifacts, log evidence, or a zero return code are
        missing.

    Examples
    --------
    Assert the act result after running the workflow::

        assert_act_result(project, code, logs, use_rust=False)
    """
    assert_ci_exercised_expected_steps(logs, use_rust=use_rust)
    if (
        "Parameter INPUT_ARTEFACT_NAME_SUFFIX specified multiple times" in logs
        and "Provided artifact name input during validation is empty" in logs
    ):
        pytest.xfail(
            "act currently fails in the shared generate-coverage composite "
            "action output/archive phase after tests and coverage succeed"
        )
    assert code == 0, logs
    assert (project / "coverage.xml").exists(), (
        "act workflow should write coverage.xml in the generated project"
    )


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
    """Validate a generated CI workflow through act.

    Parameters
    ----------
    act_ready
        Fixture that skips the test unless act validation is explicitly enabled
        and a compatible runtime is reachable.
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory for the rendered project and act artifacts.
    name
        Project name passed to the Copier template.
    package
        Package name passed to the Copier template.
    use_rust
        Whether to render the Rust-extension variant.
    artifact_dir
        Directory name, under ``tmp_path``, used for act artifacts.

    Returns
    -------
    None
        The test passes after the workflow runs and the expected generated
        workflow contract is observed.

    Raises
    ------
    AssertionError
        Raised when generated workflow content or act observations are missing.

    Examples
    --------
    Run this parametrized test with local act validation enabled::

        RUN_ACT_VALIDATION=1 python -m pytest -m act -v
    """
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
    assert "leynos/shared-actions/.github/actions/generate-coverage" in workflow, (
        "Generated workflow should use the shared generate-coverage action"
    )
    if use_rust:
        assert "cargo-manifest: rust_extension/Cargo.toml" in workflow, (
            "Rust workflow should pass the Rust extension manifest to coverage"
        )
    assert_act_result(project, code, logs, use_rust=use_rust)
