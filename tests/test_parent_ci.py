"""Validate parent repository CI workflow contracts."""

from __future__ import annotations

import re
from pathlib import Path

from tests.helpers.generated_files import read_generated_text

REPO_ROOT = Path(__file__).resolve().parent.parent

# Dependabot owns these pins; contract tests assert the action path and that
# it is pinned to a full 40-hex commit SHA, but not which SHA. See
# docs/adr-005-assert-workflow-shape-not-shas.md.
_INSTALL_MDTABLEFIX_USES_RE = re.compile(
    r"^\s*uses: leynos/shared-actions/\.github/actions/install-mdtablefix@"
    r"[0-9a-f]{40}$",
    re.MULTILINE,
)
_MARKDOWNLINT_CLI2_ACTION_USES_RE = re.compile(
    r"^\s*uses: DavidAnson/markdownlint-cli2-action@[0-9a-f]{40}",
    re.MULTILINE,
)

# The estate `markdown-formatting-baseline` rule has the parent workflows lint
# Markdown through the pinned `DavidAnson/markdownlint-cli2-action`, whose
# release carries the linter and its whole dependency graph. No parent job may
# therefore install the linter from the npm registry, and no parent job needs a
# markdownlint-cli2 version pin of its own.
_NPM_MARKDOWNLINT_CLI2_INSTALL = (
    'npm install -g "markdownlint-cli2@${MARKDOWNLINT_CLI2_VERSION}"'
)


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
    assert "MBAKE_VERSION: 1.4.6" in ci_workflow, "expected parent CI to pin mbake"
    assert _NPM_MARKDOWNLINT_CLI2_INSTALL not in ci_workflow, (
        "expected parent CI not to install markdownlint-cli2 through npm, because "
        "the pinned markdownlint-cli2 action provides it"
    )
    assert "MARKDOWNLINT_CLI2_VERSION" not in ci_workflow, (
        "expected parent CI not to pin markdownlint-cli2 itself, because the "
        "pinned markdownlint-cli2 action carries its own version"
    )
    assert 'uv tool install "mbake==${MBAKE_VERSION}"' in ci_workflow, (
        "expected parent CI to install pinned mbake"
    )
    assert "make test\n" in ci_workflow, (
        "expected parent CI to run the normal parent test gate"
    )
    assert "make spelling\n" in ci_workflow, (
        "expected parent CI to run the spelling gate"
    )
    assert "uv tool install mdformat-all" not in ci_workflow, (
        "expected parent CI not to install mdformat-all through uv"
    )
    # The estate `markdown-formatting-baseline` rule requires the parent CI to
    # install the pinned mdtablefix, run `make check-fmt`, and lint Markdown
    # through the pinned markdownlint-cli2 action.
    assert _INSTALL_MDTABLEFIX_USES_RE.search(ci_workflow), (
        "expected parent CI to install mdtablefix pinned to a full "
        "40-character commit SHA"
    )
    assert 'version: "0.6.0"' in ci_workflow, (
        "expected parent CI to pin mdtablefix at 0.6.0 or later"
    )
    assert "make check-fmt\n" in ci_workflow, (
        "expected parent CI to run the formatting gate"
    )
    assert _MARKDOWNLINT_CLI2_ACTION_USES_RE.search(ci_workflow), (
        "expected parent CI to lint Markdown through markdownlint-cli2-action "
        "pinned to a full 40-character commit SHA"
    )
    assert "globs: '**/*.md'" in ci_workflow, (
        "expected parent CI to lint every Markdown file"
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
    assert _NPM_MARKDOWNLINT_CLI2_INSTALL not in act_workflow, (
        "expected parent act-validation workflow not to install markdownlint-cli2 "
        "through npm, because the pinned markdownlint-cli2 action provides it"
    )
    assert "MARKDOWNLINT_CLI2_VERSION" not in act_workflow, (
        "expected parent act-validation workflow not to pin markdownlint-cli2 "
        "itself, because the pinned markdownlint-cli2 action carries its own version"
    )
    assert _MARKDOWNLINT_CLI2_ACTION_USES_RE.search(act_workflow), (
        "expected parent act-validation workflow to lint Markdown through "
        "markdownlint-cli2-action pinned to a full 40-character commit SHA"
    )
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
    assert "ACT_GITHUB_TOKEN: ${{ github.token }}" in act_workflow, (
        "expected parent act-validation workflow to expose github.token only to "
        "nested act tests"
    )
    assert "make test WITH_ACT=1" in act_workflow, (
        "expected parent act-validation workflow to run parent tests with act enabled"
    )
