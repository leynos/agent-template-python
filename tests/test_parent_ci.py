"""Validate parent repository CI workflow contracts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.helpers.ci_contracts import assert_go_toolchain_contract
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
    assert_go_toolchain_contract(ci_workflow, "parent CI workflow")
    assert_go_toolchain_contract(act_workflow, "parent Act workflow")

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
    assert 'version: "0.6.1"' in ci_workflow, (
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
    assert _INSTALL_MDTABLEFIX_USES_RE.search(act_workflow), (
        "expected act-validation to install pinned mdtablefix before generated gates"
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


def _synthetic_go_workflow(scenario: str) -> str:
    """Build a small workflow for Go toolchain contract edge cases."""
    include_setup = scenario != "missing setup"
    setup_before_install = scenario != "misordered setup"
    setup_ref = "v6" if scenario == "mutable action ref" else "a" * 40
    if scenario == "unsupported version":
        go_version = "1.24.x"
    elif scenario == "newer supported version":
        go_version = "1.26.0"
    else:
        go_version = "1.25.x"
    cache = "true" if scenario == "module caching enabled" else "false"
    setup_step = (
        "      - name: Set up Go\n"
        f"        uses: actions/setup-go@{setup_ref}\n"
        "        with:\n"
        f"          go-version: '{go_version}'\n"
        f"          cache: {cache}\n"
    )
    install_step = (
        "      - name: Install CLI tools\n"
        "        run: |\n"
        "          go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12\n"
        '          echo "$(go env GOPATH)/bin" >> "$GITHUB_PATH"\n'
    )
    steps = (
        (setup_step + install_step)
        if setup_before_install
        else (install_step + setup_step)
    )
    if not include_setup:
        steps = install_step
    workflow_header = (
        "name: Contract test\njobs:\n  lint:\n    runs-on: ubuntu-latest\n    steps:\n"
    )
    return workflow_header + steps


def test_parent_ci_go_contract_accepts_newer_supported_version() -> None:
    """The minimum stays stable when CI selects a later supported Go release."""
    assert_go_toolchain_contract(
        _synthetic_go_workflow("newer supported version"), "synthetic newer Go"
    )


@pytest.mark.parametrize(
    ("scenario", "expected_error"),
    [
        ("missing setup", "set up Go before every Go invocation"),
        ("misordered setup", "set up Go before every Go invocation"),
        ("unsupported version", "at least 1.25.0"),
        ("module caching enabled", "disable module caching"),
        ("mutable action ref", "full 40-hex SHA"),
    ],
    ids=["missing", "misordered", "old-version", "cache", "sha-shape"],
)
def test_parent_ci_go_contract_rejects_invalid_setup(
    scenario: str, expected_error: str
) -> None:
    """The shared Go contract catches missing or weakened setup requirements."""
    with pytest.raises(AssertionError, match=expected_error):
        assert_go_toolchain_contract(
            _synthetic_go_workflow(scenario), f"synthetic {scenario}"
        )
