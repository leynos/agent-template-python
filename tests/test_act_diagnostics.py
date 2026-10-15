"""Exercise Act result classification without a container runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pytest_copier.plugin import CopierProject

from tests.test_github_actions_integration import (
    GENERATE_COVERAGE_STEP,
    assert_act_result,
    iter_json_log_events,
    run_act,
)


def act_event(
    message: str,
    *,
    step: str = GENERATE_COVERAGE_STEP,
    step_id: str = "python",
    result: str = "",
    stage: str = "Main",
) -> str:
    """Encode a synthetic event using Act's nested composite step schema.

    Parameters
    ----------
    message
        Act message or command output.
    step
        Top-level workflow step name.
    step_id
        Nested composite step ID.
    result
        Optional explicit step result.
    stage
        Act execution stage.

    Returns
    -------
    str
        One JSON event line.

    Examples
    --------
    Model a successful coverage Python step::

        event = act_event("Success - Main python", result="success")
    """
    return json.dumps(
        {
            "stage": stage,
            "step": step,
            "stepID": ["15", step_id],
            "msg": message,
            "stepResult": result,
        }
    )


def coverage_events(*, use_rust: bool) -> list[str]:
    """Return successful coverage evidence for a pure or mixed project.

    Parameters
    ----------
    use_rust
        Whether Rust test success is required.

    Returns
    -------
    list[str]
        Ordered test completion and coverage output events.

    Examples
    --------
    Build a pure-Python workflow's successful observations::

        events = coverage_events(use_rust=False)
    """
    events = [act_event("Success - Main python", result="success")]
    if use_rust:
        events.append(
            act_event("Success - Main rust", step_id="rust", result="success")
        )
    events.append(act_event("Wrote XML report to coverage.xml"))
    return events


def archive_events() -> list[str]:
    """Return the known output/archive failure events.

    Returns
    -------
    list[str]
        Errors and explicit failures from coverage output and archival.

    Examples
    --------
    Append the known failure after successful test evidence::

        events = coverage_events(use_rust=False) + archive_events()
    """
    return [
        act_event(
            "Parameter INPUT_ARTEFACT_NAME_SUFFIX specified multiple times",
            step_id="out",
        ),
        act_event("Failure - Main out", step_id="out", result="failure"),
        act_event(
            "Provided artifact name input during validation is empty",
            step_id="15",
        ),
        act_event("Failure - Main Archive coverage", step_id="15", result="failure"),
    ]


@pytest.fixture
def coverage_project(tmp_path: Path) -> Path:
    """Provide a directory containing a valid Cobertura report."""
    (tmp_path / "coverage.xml").write_text(
        '<coverage line-rate="1"><packages><package name="example" />'
        "</packages></coverage>",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    ("step", "error", "code"),
    [
        ("Install CLI tools", "go: command not found", 127),
        ("Check formatting", "make: check-fmt failed", 2),
    ],
    ids=["missing-go-before-coverage", "other-early-failure"],
)
def test_early_failure_reports_step_before_missing_coverage(
    tmp_path: Path, step: str, error: str, code: int
) -> None:
    """Report the actual workflow failure instead of a coverage symptom."""
    logs = "\n".join(
        [
            act_event(error, step=step, step_id="3"),
            act_event("Failure", step=step, step_id="3", result="failure"),
        ]
    )
    with pytest.raises(AssertionError, match=f"return code {code}") as caught:
        assert_act_result(tmp_path, code, logs, use_rust=False)
    message = str(caught.value)
    assert f"stage=Main; step={step}; stepID=['15', '3']" in message
    assert error in message
    assert "Complete Act logs:\n" + logs in message
    assert "coverage action step was not observed" not in message


def test_nonfatal_error_is_not_reported_as_failed_step(tmp_path: Path) -> None:
    """Select the first failure result, despite earlier cache warnings."""
    logs = "\n".join(
        [
            act_event("cargo metadata failed", step="Cache Rust lint and test tools"),
            act_event(
                "Success", step="Cache Rust lint and test tools", result="success"
            ),
            act_event("lint failed", step="Run source and action lints"),
            act_event("Failure", step="Run source and action lints", result="failure"),
            act_event("Failure", step="Archive coverage", result="failure"),
        ]
    )
    with pytest.raises(AssertionError, match="First failed step:.*Run source"):
        assert_act_result(tmp_path, 1, logs, use_rust=True)


def test_nonzero_without_step_result_preserves_evidence(tmp_path: Path) -> None:
    """Avoid guessing a failed step when Act supplies no structured result."""
    logs = 'unstructured runtime error\n{"level": "error", "msg": "failure"}'
    with pytest.raises(AssertionError, match="No stepResult=failure") as caught:
        assert_act_result(tmp_path, 1, logs, use_rust=False)
    assert logs in str(caught.value)


def test_success_without_coverage_evidence_is_rejected(coverage_project: Path) -> None:
    """A zero exit code and XML cannot replace observed coverage execution."""
    logs = act_event("Success - Main python", result="success")
    with pytest.raises(AssertionError, match="coverage action step was not observed"):
        assert_act_result(coverage_project, 0, logs, use_rust=False)


@pytest.mark.parametrize("use_rust", [False, True], ids=["pure-python", "rust"])
def test_success_requires_language_and_coverage_evidence(
    coverage_project: Path, use_rust: bool
) -> None:
    """Accept successful language steps with coverage evidence and valid XML."""
    logs = "\n".join(coverage_events(use_rust=use_rust))
    assert_act_result(coverage_project, 0, logs, use_rust=use_rust)


def test_rust_success_requires_rust_tests(coverage_project: Path) -> None:
    """Reject a mixed workflow that has only Python test success."""
    logs = "\n".join(coverage_events(use_rust=False))
    with pytest.raises(AssertionError, match="successful Rust tests"):
        assert_act_result(coverage_project, 0, logs, use_rust=True)


@pytest.mark.parametrize("use_rust", [False, True], ids=["pure-python", "rust"])
def test_archive_exception_requires_prior_success(
    coverage_project: Path, use_rust: bool
) -> None:
    """Allow the known archive issue only after successful test and coverage work."""
    logs = "\n".join(coverage_events(use_rust=use_rust) + archive_events())
    with pytest.raises(
        pytest.xfail.Exception, match="after tests and coverage succeed"
    ):
        assert_act_result(coverage_project, 1, logs, use_rust=use_rust)


@pytest.mark.parametrize(
    "early_step",
    ["Install CLI tools", "Run source and action lints", GENERATE_COVERAGE_STEP],
)
def test_archive_text_cannot_hide_earlier_failure(
    coverage_project: Path, early_step: str
) -> None:
    """Matching archive strings never turn an earlier failed step into an xfail."""
    logs = "\n".join(
        [act_event("Failure", step=early_step, step_id="python", result="failure")]
        + coverage_events(use_rust=False)
        + archive_events()
    )
    with pytest.raises(AssertionError, match="First failed step"):
        assert_act_result(coverage_project, 1, logs, use_rust=False)


def test_archive_error_without_tests_or_coverage_is_rejected(tmp_path: Path) -> None:
    """Archive error text alone cannot qualify for the known exception."""
    with pytest.raises(AssertionError, match="Coverage contract"):
        assert_act_result(tmp_path, 1, "\n".join(archive_events()), use_rust=False)


@pytest.mark.parametrize(
    "report",
    [None, "<coverage>", "<unrelated />", "<coverage><packages /></coverage>"],
    ids=["missing", "malformed", "wrong-document", "empty-packages"],
)
@pytest.mark.parametrize("code", [0, 1], ids=["success", "archive-failure"])
def test_result_requires_valid_coverage_xml(
    tmp_path: Path, report: str | None, code: int
) -> None:
    """Both successful runs and archive exceptions require a real coverage report."""
    if report is not None:
        (tmp_path / "coverage.xml").write_text(report, encoding="utf-8")
    events = coverage_events(use_rust=False)
    if code:
        events += archive_events()
    with pytest.raises(AssertionError, match="coverage.xml"):
        assert_act_result(tmp_path, code, "\n".join(events), use_rust=False)


def test_command_echo_is_not_test_success(coverage_project: Path) -> None:
    """A printed test command does not prove that its tests succeeded."""
    logs = "\n".join(
        [act_event("uv run run_python.py; pytest -v; coverage.xml")] + archive_events()
    )
    with pytest.raises(AssertionError, match="successful Python tests"):
        assert_act_result(coverage_project, 1, logs, use_rust=False)


def test_json_event_reader_ignores_non_object_and_malformed_lines() -> None:
    """Retain real JSON event objects without interpreting unrelated output."""
    logs = 'plain output\n[]\n{"incomplete"\n' + act_event("message")
    assert iter_json_log_events(logs) == [json.loads(act_event("message"))]


def test_archive_exception_allows_parent_failure_propagation(
    coverage_project: Path,
) -> None:
    """Treat the failed coverage composite as propagation of its archive failure."""
    ancestor = json.dumps(
        {
            "stage": "Main",
            "step": GENERATE_COVERAGE_STEP,
            "stepID": ["15"],
            "stepResult": "failure",
            "msg": "Failure - Main Test and Measure Coverage",
        }
    )
    logs = "\n".join(coverage_events(use_rust=False) + archive_events() + [ancestor])
    with pytest.raises(
        pytest.xfail.Exception, match="after tests and coverage succeed"
    ):
        assert_act_result(coverage_project, 1, logs, use_rust=False)


def test_archive_exception_rejects_independent_later_failure(
    coverage_project: Path,
) -> None:
    """A valid archive exception cannot hide another failing workflow step."""
    logs = "\n".join(
        coverage_events(use_rust=False)
        + archive_events()
        + [act_event("Failure", step="Save results", result="failure")]
    )
    with pytest.raises(AssertionError, match="return code 1"):
        assert_act_result(coverage_project, 1, logs, use_rust=False)


def test_success_with_archive_error_text_does_not_xfail(
    coverage_project: Path,
) -> None:
    """The archive exception applies only to a non-zero workflow result."""
    messages = [
        act_event("Parameter INPUT_ARTEFACT_NAME_SUFFIX specified multiple times"),
        act_event("Provided artifact name input during validation is empty"),
    ]
    logs = "\n".join(coverage_events(use_rust=False) + messages)
    assert_act_result(coverage_project, 0, logs, use_rust=False)


def test_archive_exception_rejects_independent_coverage_root(
    coverage_project: Path,
) -> None:
    """A similarly named composite at another root is an independent failure."""
    unrelated = json.dumps(
        {
            "stage": "Main",
            "step": GENERATE_COVERAGE_STEP,
            "stepID": ["99"],
            "stepResult": "failure",
            "msg": "Failure - Main Test and Measure Coverage",
        }
    )
    logs = "\n".join(coverage_events(use_rust=False) + archive_events() + [unrelated])
    with pytest.raises(AssertionError, match="return code 1"):
        assert_act_result(coverage_project, 1, logs, use_rust=False)


def test_lowercase_step_ids_preserve_archive_classification(
    coverage_project: Path,
) -> None:
    """Accept Act's lowercase stepid spelling under the same strict contract."""
    events = []
    for line in coverage_events(use_rust=True) + archive_events():
        event = json.loads(line)
        event["stepid"] = event.pop("stepID")
        events.append(json.dumps(event))
    with pytest.raises(
        pytest.xfail.Exception, match="after tests and coverage succeed"
    ):
        assert_act_result(coverage_project, 1, "\n".join(events), use_rust=True)


def test_run_act_preserves_cross_stream_failure_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Diagnose the earlier stderr failure before a later stdout failure."""
    early = act_event(
        "Failure from stderr",
        step="Earlier stderr step",
        step_id="3",
        result="failure",
    )
    later = act_event(
        "Failure from stdout",
        step="Later stdout step",
        step_id="4",
        result="failure",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "act"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"print({early!r}, file=sys.stderr, flush=True)\n"
        f"print({later!r}, file=sys.stdout, flush=True)\n"
        "sys.exit(127)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setattr(
        "tests.test_github_actions_integration.docker_environment",
        lambda: {"PATH": str(bin_dir)},
    )
    monkeypatch.setattr(
        "tests.test_github_actions_integration.container_daemon_socket",
        lambda _: None,
    )
    project = cast("CopierProject", SimpleNamespace(path=tmp_path))
    artifact_dir = tmp_path / "artefacts"

    code, logs = run_act(project, artifact_dir=artifact_dir)

    assert code == 127
    assert logs.splitlines() == [early, later]
    assert (artifact_dir / "act.log").read_text(encoding="utf-8") == logs
    with pytest.raises(
        AssertionError,
        match="First failed step: stage=Main; step=Earlier stderr step",
    ):
        assert_act_result(tmp_path, code, logs, use_rust=False)
