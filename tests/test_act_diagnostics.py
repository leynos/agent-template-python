"""Exercise Act diagnostics with synthetic events and no container runtime.

Drive ``assert_act_result`` with synthetic Act JSON traces to check failed-step
reporting, coverage requirements, and the narrow archive-phase exception. A
fake executable also exercises ``run_act`` and its retained, ordered logs.
Named regressions and generated trace variations run without Docker or network
access.

Examples
--------
Run this module's diagnostic checks::

    python -m pytest tests/test_act_diagnostics.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from string import ascii_lowercase
from types import SimpleNamespace
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pytest_copier.plugin import CopierFixture, CopierProject

from tests import test_github_actions_integration as act_integration
from tests.test_github_actions_integration import (
    GENERATE_COVERAGE_STEP,
    assert_act_result,
    is_archive_failure,
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
    assert f"stage=Main; step={step}; stepID=['15', '3']" in message, (
        "diagnostic should identify the first failed step"
    )
    assert error in message, "diagnostic should include nearby error output"
    assert "Complete Act logs:\n" + logs in message, (
        "diagnostic should retain the complete Act log"
    )
    assert "coverage action step was not observed" not in message, (
        "missing coverage should not mask an earlier workflow failure"
    )


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
    assert logs in str(caught.value), "unstructured failure evidence should be retained"


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


def test_archive_text_cannot_hide_cargo_nextest_checksum_failure(
    coverage_project: Path,
) -> None:
    """Reject an installer checksum failure despite later valid coverage evidence."""
    mismatch = (
        "cargo-nextest checksum mismatch: expected trusted digest, got other digest"
    )
    installer = {
        "stage": "Main",
        "step": GENERATE_COVERAGE_STEP,
        "stepID": ["16", "7"],
        "msg": mismatch,
    }
    failed_installer = {
        **installer,
        "msg": "Failure - Main Install cargo-nextest",
        "stepResult": "failure",
    }
    later = iter_json_log_events(
        "\n".join(coverage_events(use_rust=True) + archive_events())
    )
    for event in later:
        cast("list[str]", event["stepID"])[0] = "16"
    logs = "\n".join(
        json.dumps(event) for event in [installer, failed_installer, *later]
    )

    with pytest.raises(AssertionError, match="Act exited with return code 1") as caught:
        assert_act_result(coverage_project, 1, logs, use_rust=True)

    message = str(caught.value)
    assert (
        "First failed step: stage=Main; step=Test and Measure Coverage; "
        "stepID=['16', '7']"
    ) in message, "diagnostic should identify the nested installer failure"
    assert mismatch in message.split("Complete Act logs:", 1)[0], (
        "nearby failure output should expose the installer checksum mismatch"
    )


def test_output_failure_with_successful_archive_is_not_an_archive_exception(
    coverage_project: Path,
) -> None:
    """Reject duplicate output inputs even when fallback coverage archival succeeds."""
    duplicate = "Parameter INPUT_ARTEFACT_NAME_SUFFIX specified multiple times"
    events = iter_json_log_events(
        "\n".join(
            coverage_events(use_rust=False)
            + [
                act_event(duplicate, step_id="out"),
                act_event("Failure - Main out", step_id="out", result="failure"),
                act_event(
                    "Success - Main Archive coverage", step_id="18", result="success"
                ),
            ]
        )
    )
    for event in events:
        cast("list[str]", event["stepID"])[0] = "14"
    events.append(
        {
            "stage": "Main",
            "step": GENERATE_COVERAGE_STEP,
            "stepID": ["14"],
            "stepResult": "failure",
            "msg": "Failure - Main Test and Measure Coverage",
        }
    )
    logs = "\n".join(json.dumps(event) for event in events)

    with pytest.raises(AssertionError, match="Act exited with return code 1") as caught:
        assert_act_result(coverage_project, 1, logs, use_rust=False)

    message = str(caught.value)
    assert (
        "First failed step: stage=Main; step=Test and Measure Coverage; "
        "stepID=['14', 'out']"
    ) in message, (
        "diagnostic should identify the output failure despite archive success"
    )
    assert duplicate in message.split("Complete Act logs:", 1)[0], (
        "nearby failure output should retain the duplicate-input error"
    )


def test_archive_protocol_failure_is_not_the_known_archive_exception(
    coverage_project: Path,
) -> None:
    """Reject artefact protocol failures after successful tests and coverage."""
    protocol_error = 'Failed to CreateArtifact: unknown field "mime_type"'
    events = iter_json_log_events(
        "\n".join(
            coverage_events(use_rust=False)
            + [
                act_event(protocol_error, step_id="19"),
                act_event(
                    "Failure - Main Archive coverage", step_id="19", result="failure"
                ),
            ]
        )
    )
    for event in events:
        cast("list[str]", event["stepID"])[0] = "14"
    events.append(
        {
            "stage": "Main",
            "step": GENERATE_COVERAGE_STEP,
            "stepID": ["14"],
            "stepResult": "failure",
            "msg": "Failure - Main Test and Measure Coverage",
        }
    )
    logs = "\n".join(json.dumps(event) for event in events)

    with pytest.raises(AssertionError, match="Act exited with return code 1") as caught:
        assert_act_result(coverage_project, 1, logs, use_rust=False)

    message = str(caught.value)
    assert (
        "First failed step: stage=Main; step=Test and Measure Coverage; "
        "stepID=['14', '19']"
    ) in message, "diagnostic should identify the failed archive protocol step"
    assert protocol_error in message.split("Complete Act logs:", 1)[0], (
        "nearby failure output should expose the artefact protocol error"
    )


@pytest.mark.parametrize("stable_evidence", [False, True], ids=["temporary", "stable"])
def test_failed_act_retains_coverage_before_result_assertion(
    coverage_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stable_evidence: bool,
) -> None:
    """Retain coverage and full logs even when the workflow result is rejected."""
    evidence_root = tmp_path / "retained" if stable_evidence else tmp_path
    if stable_evidence:
        monkeypatch.setenv("ACT_EVIDENCE_DIR", str(evidence_root))
    else:
        monkeypatch.delenv("ACT_EVIDENCE_DIR", raising=False)
    workflow_dir = coverage_project / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        "uses: leynos/shared-actions/.github/actions/generate-coverage@fixture\n",
        encoding="utf-8",
    )
    logs = act_event("Failure - Main setup", step="Set up tools", result="failure")

    def failed_act(_project: CopierProject, *, artifact_dir: Path) -> tuple[int, str]:
        """Retain the same diagnostic output as a failed Act subprocess."""
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "act.log").write_text(logs, encoding="utf-8")
        return 1, logs

    monkeypatch.setattr(act_integration, "prepare_git_repository", lambda _: None)
    monkeypatch.setattr(act_integration, "run_act", failed_act)
    copier = cast(
        "CopierFixture",
        SimpleNamespace(copy=lambda *_args, **_kwargs: coverage_project),
    )
    with pytest.raises(AssertionError, match="Act exited with return code 1"):
        act_integration.test_generated_workflow_runs_with_shared_coverage_action(
            act_ready=None,
            copier=copier,
            tmp_path=tmp_path,
            name="Evidence",
            package="evidence",
            use_rust=False,
            artifact_dir="pure-artefacts",
        )

    retained = evidence_root / "pure-artefacts"
    assert (retained / "coverage.xml").read_bytes() == (
        coverage_project / "coverage.xml"
    ).read_bytes(), "coverage should survive failure outside the rendered project"
    assert (retained / "act.log").read_text(encoding="utf-8") == logs, (
        "the evidence directory should retain complete failure logs"
    )


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
    assert iter_json_log_events(logs) == [json.loads(act_event("message"))], (
        "event parsing should keep only complete JSON objects"
    )


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

    assert code == 127, "run_act should preserve the subprocess exit code"
    assert logs.splitlines() == [early, later], (
        "combined logs should preserve cross-stream failure order"
    )
    assert (artifact_dir / "act.log").read_text(encoding="utf-8") == logs, (
        "retained logs should match the ordered output used for diagnostics"
    )
    with pytest.raises(
        AssertionError,
        match="First failed step: stage=Main; step=Earlier stderr step",
    ):
        assert_act_result(tmp_path, code, logs, use_rust=False)


@st.composite
def varied_archive_traces(draw: st.DrawFn) -> list[dict[str, object]]:
    """Generate known archive traces with harmless structural variations.

    Parameters
    ----------
    draw
        Hypothesis callback for generating each trace component.

    Returns
    -------
    list[dict[str, object]]
        A known archive failure with arbitrary root and nested IDs, reordered
        archive events, irrelevant output, and optional parent propagation.

    Examples
    --------
    Supply generated traces to a classifier property::

        traces = varied_archive_traces()
    """
    root = str(draw(st.integers(min_value=0, max_value=1_000_000)))
    nested = draw(
        st.lists(st.text(ascii_lowercase, min_size=1, max_size=8), max_size=3)
    )
    events = iter_json_log_events("\n".join(archive_events()))
    for event in events:
        original = cast("list[str]", event["stepID"])
        event["stepID"] = [root, *nested, *original[1:]]
    events = list(draw(st.permutations(events)))
    noise = draw(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=20),
                st.text(ascii_lowercase + " ", max_size=40),
            ),
            max_size=5,
        )
    )
    for position, message in noise:
        events.insert(
            position % (len(events) + 1),
            {"level": "error", "msg": f"Non-terminating cache error: {message}"},
        )
    if draw(st.booleans()):
        events.append(
            {
                "stage": "Main",
                "step": GENERATE_COVERAGE_STEP,
                "stepID": [root],
                "stepResult": "failure",
                "msg": "Failure - Main Test and Measure Coverage",
            }
        )
    if draw(st.booleans()):
        for event in events:
            if "stepID" in event:
                event["stepid"] = event.pop("stepID")
    return events


@given(trace=varied_archive_traces())
def test_archive_classification_survives_harmless_trace_variations(
    trace: list[dict[str, object]],
) -> None:
    """Root renaming, harmless output, and archive ordering preserve acceptance."""
    assert is_archive_failure(trace), (
        "known archive failures should survive irrelevant trace variations"
    )


@given(
    trace=varied_archive_traces(),
    violation=st.sampled_from(
        [
            "independent-failure",
            "wrong-root",
            "wrong-stage",
            "missing-output-error",
            "missing-archive-error",
        ]
    ),
    position=st.integers(min_value=0, max_value=20),
)
def test_archive_classification_rejects_one_illegal_trace_change(
    trace: list[dict[str, object]], violation: str, position: int
) -> None:
    """One independent failure or broken archive prerequisite forbids acceptance."""
    events = [dict(event) for event in trace]
    failure = next(event for event in events if event.get("stepResult") == "failure")
    if violation == "independent-failure":
        events.insert(
            position % (len(events) + 1),
            {
                "stage": "Main",
                "step": "Independent workflow step",
                "stepID": ["unrelated"],
                "stepResult": "failure",
                "msg": "Failure - Main Independent workflow step",
            },
        )
    elif violation == "wrong-root":
        # Keep the first failure's anchor intact; move only a second failure.
        changed = next(
            event
            for event in events
            if event is not failure and event.get("stepResult") == "failure"
        )
        key = "stepID" if "stepID" in changed else "stepid"
        path = cast("list[str]", changed[key])
        changed[key] = ["different-root", *path[1:]]
    elif violation == "wrong-stage":
        failure["stage"] = "Post"
    else:
        missing = (
            "Parameter INPUT_ARTEFACT_NAME_SUFFIX specified multiple times"
            if violation == "missing-output-error"
            else "Provided artifact name input during validation is empty"
        )
        events = [event for event in events if event.get("msg") != missing]
    assert not is_archive_failure(events), (
        f"archive classification should reject the illegal change: {violation}"
    )


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (b"partial bytes\n", "partial bytes\n"),
        ("partial text\n", "partial text\n"),
        (None, ""),
        (b"partial \xff output\n", "partial \ufffd output\n"),
    ],
    ids=["bytes", "text", "no-output", "invalid-utf8"],
)
def test_run_act_retains_partial_output_and_reraises_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    output: bytes | str | None,
    expected: str,
) -> None:
    """Retain partial combined output without replacing the timeout exception."""
    failure = subprocess.TimeoutExpired("act", 1200, output=output)

    def timed_out_run(
        _command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        """Model a subprocess timeout carrying its partial combined output."""
        raise failure

    monkeypatch.setattr(act_integration, "docker_environment", dict)
    monkeypatch.setattr(act_integration, "container_daemon_socket", lambda _: None)
    monkeypatch.setattr(subprocess, "run", timed_out_run)
    project = cast("CopierProject", SimpleNamespace(path=tmp_path))
    artifact_dir = tmp_path / "artefacts"

    with pytest.raises(subprocess.TimeoutExpired, match="timed out") as caught:
        run_act(project, artifact_dir=artifact_dir)

    assert caught.value is failure, "run_act should propagate the original timeout"
    assert (artifact_dir / "act.log").read_text(encoding="utf-8") == expected, (
        "timeout evidence should retain decoded partial output, including replacements"
    )


@pytest.mark.parametrize("stable_evidence", [False, True], ids=["temporary", "stable"])
@pytest.mark.parametrize("failure_kind", ["timeout", "other-error"])
def test_raising_act_retains_coverage_before_propagating_exception(
    coverage_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stable_evidence: bool,
    failure_kind: str,
) -> None:
    """Export existing coverage when Act raises before creating its evidence directory."""
    evidence_root = tmp_path / "retained" if stable_evidence else tmp_path
    if stable_evidence:
        monkeypatch.setenv("ACT_EVIDENCE_DIR", str(evidence_root))
    else:
        monkeypatch.delenv("ACT_EVIDENCE_DIR", raising=False)
    failure = (
        subprocess.TimeoutExpired("act", 1200)
        if failure_kind == "timeout"
        else RuntimeError("Act seam failure")
    )

    def raising_act(_project: CopierProject, *, artifact_dir: Path) -> tuple[int, str]:
        """Raise before the usual subprocess evidence directory is created."""
        assert not artifact_dir.exists(), "the caller should handle a missing directory"
        raise failure

    monkeypatch.setattr(act_integration, "prepare_git_repository", lambda _: None)
    monkeypatch.setattr(act_integration, "run_act", raising_act)
    copier = cast(
        "CopierFixture",
        SimpleNamespace(copy=lambda *_args, **_kwargs: coverage_project),
    )
    expected_message = "timed out" if failure_kind == "timeout" else "Act seam failure"
    with pytest.raises(type(failure), match=expected_message) as caught:
        act_integration.test_generated_workflow_runs_with_shared_coverage_action(
            act_ready=None,
            copier=copier,
            tmp_path=tmp_path,
            name="Evidence",
            package="evidence",
            use_rust=False,
            artifact_dir="pure-artefacts",
        )

    assert caught.value is failure, "the caller should preserve the original exception"
    assert (evidence_root / "pure-artefacts" / "coverage.xml").read_bytes() == (
        coverage_project / "coverage.xml"
    ).read_bytes(), "coverage should be exported even when Act raises"
