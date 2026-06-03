"""Validate parent repository CI workflow contracts."""

from __future__ import annotations

from pathlib import Path

from tests.helpers.generated_files import read_generated_text

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_parent_ci_splits_application_and_act_validation_tests() -> None:
    """Validate parent CI splits normal and act-enabled test gates.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when the parent CI workflow runs normal tests and the
        separate act-validation workflow installs act prerequisites before
        running ``make test WITH_ACT=1``.
    """
    ci_workflow = read_generated_text(REPO_ROOT / ".github" / "workflows" / "ci.yml")
    act_workflow = read_generated_text(
        REPO_ROOT / ".github" / "workflows" / "act-validation.yml"
    )

    assert "make test\n" in ci_workflow, (
        "expected parent CI to run the normal parent test gate"
    )
    assert "make test WITH_ACT=1" not in ci_workflow, (
        "expected parent CI to leave act validation to a separate workflow"
    )
    assert "ACT_VERSION: v0.2.80" in act_workflow, (
        "expected parent act-validation workflow to pin the act release"
    )
    assert "act_Linux_x86_64.tar.gz" in act_workflow, (
        "expected parent act-validation workflow to install the act Linux binary"
    )
    assert "docker info" in act_workflow, (
        "expected parent act-validation workflow to verify Docker before act tests"
    )
    assert "make test WITH_ACT=1" in act_workflow, (
        "expected parent act-validation workflow to run parent tests with act enabled"
    )
