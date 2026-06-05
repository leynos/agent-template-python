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

    assert "permissions:\n  contents: read" in ci_workflow, (
        "expected parent CI to restrict GITHUB_TOKEN to repository contents reads"
    )
    assert "MARKDOWNLINT_CLI2_VERSION: 0.22.1" in ci_workflow, (
        "expected parent CI to pin markdownlint-cli2"
    )
    assert "MBAKE_VERSION: 1.4.6" in ci_workflow, "expected parent CI to pin mbake"
    assert 'npm install -g "markdownlint-cli2@${MARKDOWNLINT_CLI2_VERSION}"' in (
        ci_workflow
    ), "expected parent CI to install pinned markdownlint-cli2"
    assert 'uv tool install "mbake==${MBAKE_VERSION}"' in ci_workflow, (
        "expected parent CI to install pinned mbake"
    )
    assert "make test\n" in ci_workflow, (
        "expected parent CI to run the normal parent test gate"
    )
    assert "uv tool install mdformat-all" not in ci_workflow, (
        "expected parent CI not to install mdformat-all through uv"
    )
    assert "mdtablefix" not in ci_workflow, (
        "expected parent CI not to install Markdown formatting tools"
    )
    assert "make test WITH_ACT=1" not in ci_workflow, (
        "expected parent CI to leave act validation to a separate workflow"
    )
    assert "permissions:\n  contents: read" in act_workflow, (
        "expected parent act-validation workflow to restrict GITHUB_TOKEN"
    )
    assert "ACT_VERSION:" in act_workflow, (
        "expected parent act-validation workflow to declare an act version"
    )
    assert "act_Linux_x86_64.tar.gz" in act_workflow, (
        "expected parent act-validation workflow to include act_Linux_x86_64.tar.gz"
    )
    assert "${ACT_VERSION}" in act_workflow, (
        "expected parent act-validation workflow to include ${ACT_VERSION}"
    )
    assert "sha256sum -c -" in act_workflow, (
        "expected parent act-validation workflow to verify the act archive checksum"
    )
    assert 'npm install -g "markdownlint-cli2@${MARKDOWNLINT_CLI2_VERSION}"' in (
        act_workflow
    ), "expected parent act-validation workflow to install pinned markdownlint-cli2"
    assert 'uv tool install "mbake==${MBAKE_VERSION}"' in act_workflow, (
        "expected parent act-validation workflow to install pinned mbake"
    )
    assert "uv tool install mdformat-all" not in act_workflow, (
        "expected parent act-validation workflow not to install mdformat-all through uv"
    )
    assert "mdtablefix" not in act_workflow, (
        "expected parent act-validation workflow not to install Markdown formatting tools"
    )
    assert "docker info" in act_workflow, (
        "expected parent act-validation workflow to verify Docker before act tests"
    )
    assert "make test WITH_ACT=1" in act_workflow, (
        "expected parent act-validation workflow to run parent tests with act enabled"
    )
