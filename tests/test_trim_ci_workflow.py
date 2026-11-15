"""Unit tests for the act coverage-job workflow trimmer.

``trim_ci_workflow`` keeps the real act run to the steps the shared coverage
action needs. These tests run without act, so a wrong trim fails in the default
suite rather than only in the act-validation job.
"""

from __future__ import annotations

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st

from tests.test_github_actions_integration import COVERAGE_JOB_STEPS, trim_ci_workflow

REMOVED_STEPS = (
    "Check formatting",
    "Run typechecker",
    "Audit dependencies",
    "Install CLI tools",
)


def _step(name: str) -> str:
    """Return a rendered-looking step block named *name*."""
    return f"      - name: {name}\n        run: echo {name.replace(' ', '-')}\n"


def _workflow(step_names: list[str]) -> str:
    """Return a minimal CI workflow whose job runs the named steps in order."""
    header = (
        "name: CI\n\n'on':\n  pull_request:\n\n"
        "jobs:\n  lint-test:\n    runs-on: ubuntu-latest\n    steps:\n"
    )
    return header + "\n".join(_step(name) for name in step_names)


def _step_names(workflow: str) -> list[str]:
    """Return the step names of the workflow's only job, parsed as YAML."""
    document = yaml.safe_load(workflow)
    return [step["name"] for step in document["jobs"]["lint-test"]["steps"]]


FULL_STEPS = [*COVERAGE_JOB_STEPS[:-1], *REMOVED_STEPS, COVERAGE_JOB_STEPS[-1]]


def test_trim_keeps_coverage_job_steps_and_drops_the_rest() -> None:
    """Only the coverage job's steps survive, in their original order."""
    trimmed = trim_ci_workflow(_workflow(FULL_STEPS))

    assert _step_names(trimmed) == list(COVERAGE_JOB_STEPS), (
        "expected the trim to keep exactly the coverage job's steps in order"
    )


def test_trim_output_is_valid_workflow_yaml() -> None:
    """The trimmed text still parses and keeps the workflow's other keys."""
    document = yaml.safe_load(trim_ci_workflow(_workflow(FULL_STEPS)))

    assert document["jobs"]["lint-test"]["runs-on"] == "ubuntu-latest", (
        "expected the trim to leave the job definition intact"
    )


@pytest.mark.parametrize("missing", ["Install code", "Test and Measure Coverage"])
def test_trim_rejects_a_workflow_missing_a_required_step(missing: str) -> None:
    """A renamed or removed required step fails loudly instead of trimming away."""
    names = [name for name in FULL_STEPS if name != missing]

    with pytest.raises(AssertionError, match="lacks coverage-job steps") as caught:
        trim_ci_workflow(_workflow(names))

    assert missing in str(caught.value), "expected the failure to name the missing step"


def test_trim_tolerates_a_pure_variant_without_the_rust_setup_step() -> None:
    """The Rust set-up step is optional: a workflow without it still trims."""
    names = [name for name in FULL_STEPS if name != "Set up Rust"]

    assert "Set up Rust" not in _step_names(trim_ci_workflow(_workflow(names))), (
        "expected the trim to accept a workflow with no Rust set-up step"
    )


def test_trim_returns_text_without_step_headers_unchanged() -> None:
    """Text with no step headers is passed through, not emptied."""
    text = "uses: leynos/shared-actions/.github/actions/generate-coverage@fixture\n"

    assert trim_ci_workflow(text) == text, (
        "expected header-less text to pass through untouched"
    )


@given(extra_count=st.integers(min_value=0, max_value=8), split=st.integers(0, 8))
def test_trim_keeps_exactly_the_required_steps_whatever_surrounds_them(
    extra_count: int, split: int
) -> None:
    """Arbitrary extra steps never survive and the required steps always do."""
    extras = [f"Extra step {number}" for number in range(extra_count)]
    cut = min(split, extra_count)
    names = [*extras[:cut], *COVERAGE_JOB_STEPS, *extras[cut:]]

    trimmed = _step_names(trim_ci_workflow(_workflow(names)))

    assert trimmed == list(COVERAGE_JOB_STEPS), (
        "expected only the coverage job's steps to survive the trim"
    )
