"""Validate parent repository CI workflow contracts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.helpers.ci_contracts import (
    assert_coverage_publication_contract,
    assert_go_toolchain_contract,
)
from tests.helpers.generated_files import (
    parse_yaml_mapping,
    read_generated_text,
    require_mapping,
    require_sequence,
)

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
_UPLOAD_ARTEFACT_USES_RE = re.compile(r"^actions/upload-artifact@[0-9a-f]{40}$")

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
    assert_go_toolchain_contract(
        ci_workflow,
        "parent CI workflow",
        actionlint_step_name="Install template test tools",
    )
    assert_go_toolchain_contract(
        act_workflow,
        "parent Act workflow",
        actionlint_step_name="Install documentation tooling",
    )
    act_jobs = require_mapping(
        parse_yaml_mapping(act_workflow, "parent Act workflow"),
        "jobs",
        "parent Act workflow",
    )
    act_job = require_mapping(act_jobs, "act-validation", "parent Act workflow jobs")
    act_steps = require_sequence(act_job, "steps", "parent Act workflow job")
    actionlint_indices = [
        index
        for index, step in enumerate(act_steps)
        if isinstance(step, dict)
        and step.get("name") == "Install documentation tooling"
        and "actionlint" in str(step.get("run", ""))
    ]
    test_indices = [
        index
        for index, step in enumerate(act_steps)
        if isinstance(step, dict) and "make test WITH_ACT=1" in str(step.get("run", ""))
    ]
    evidence_test_steps = [
        step
        for step in act_steps
        if isinstance(step, dict)
        and step.get("name") == "Run template tests with act validation"
    ]
    assert len(evidence_test_steps) == 1, (
        "expected parent Act workflow to run template tests once"
    )
    evidence_test_env = require_mapping(
        evidence_test_steps[0], "env", "Act template tests step"
    )
    assert evidence_test_env.get("ACT_EVIDENCE_DIR") == (
        "${{ runner.temp }}/act-evidence"
    ), "expected Act tests to write evidence under runner.temp"

    evidence_upload_indices = [
        index
        for index, step in enumerate(act_steps)
        if isinstance(step, dict) and step.get("name") == "Upload Act coverage evidence"
    ]
    assert len(evidence_upload_indices) == 1, (
        "expected parent Act workflow to upload coverage evidence once"
    )
    evidence_upload = act_steps[evidence_upload_indices[0]]
    evidence_upload_uses = evidence_upload.get("uses")
    assert isinstance(evidence_upload_uses, str) and (
        _UPLOAD_ARTEFACT_USES_RE.fullmatch(evidence_upload_uses)
    ), "expected Act evidence upload to pin actions/upload-artifact to a full SHA"
    assert evidence_upload.get("if") == "always()", (
        "expected Act coverage evidence to upload after failed tests"
    )
    evidence_inputs = require_mapping(
        evidence_upload, "with", "Act evidence upload step"
    )
    assert evidence_inputs.get("name") == "act-coverage-evidence", (
        "expected Act evidence artefact name to be stable"
    )
    expected_evidence_paths = [
        "${{ runner.temp }}/act-evidence/pure-artefacts/coverage.xml",
        "${{ runner.temp }}/act-evidence/rust-artefacts/coverage.xml",
    ]
    actual_evidence_paths = str(evidence_inputs.get("path", "")).splitlines()
    assert actual_evidence_paths == expected_evidence_paths, (
        "expected the upload to include both exact Act coverage report paths"
    )
    assert evidence_inputs.get("if-no-files-found") == "error", (
        "expected Act evidence upload to fail when no coverage reports exist"
    )
    assert len(actionlint_indices) == 1, (
        "expected parent Act workflow to install Actionlint once"
    )
    assert len(test_indices) == 1, "expected parent Act workflow to run tests once"
    assert actionlint_indices[0] < test_indices[0], (
        "expected parent Act workflow to install Actionlint before tests"
    )
    assert evidence_upload_indices[0] > test_indices[0], (
        "expected parent Act workflow to upload evidence after template tests"
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


def _synthetic_coverage_workflow(publish_condition: str | None) -> str:
    """Build a minimal workflow for the Act coverage-publication contract."""
    publication_input = (
        ""
        if publish_condition is None
        else f"          publish-artefact: {publish_condition}\n"
    )
    generated_ref = "a" * 40
    return (
        "name: Coverage contract\n"
        "jobs:\n"
        "  coverage:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Generate coverage\n"
        "        uses: leynos/shared-actions/.github/actions/generate-coverage@"
        f"{generated_ref}\n"
        "        with:\n"
        f"{publication_input}"
        "          output-path: coverage.xml\n"
    )


def test_coverage_publication_contract_accepts_act_only_condition() -> None:
    """Whitespace around the Act-only condition does not change its contract."""
    workflow = _synthetic_coverage_workflow("${{   env.ACT   !=   'true'   }}")
    assert_coverage_publication_contract(workflow, "synthetic coverage workflow")


@pytest.mark.parametrize(
    "publish_condition",
    [
        None,
        "false",
        "true",
        "${{ env.ACT == 'true' }}",
    ],
    ids=["missing", "always-false", "always-true", "inverse-act-condition"],
)
def test_coverage_publication_contract_rejects_unsafe_condition(
    publish_condition: str | None,
) -> None:
    """Reject conditions that drop hosted evidence or publish from local Act."""
    with pytest.raises(AssertionError, match="publish-artefact"):
        assert_coverage_publication_contract(
            _synthetic_coverage_workflow(publish_condition),
            "synthetic coverage workflow",
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
    install_step_name = (
        scenario
        if scenario == "wrong Actionlint step identity"
        else "Install CLI tools"
    )
    install_step = (
        f"      - name: {install_step_name}\n"
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
        _synthetic_go_workflow("newer supported version"),
        "synthetic newer Go",
        actionlint_step_name="Install CLI tools",
    )


@pytest.mark.parametrize(
    ("scenario", "expected_error"),
    [
        ("missing setup", "set up Go before every Go invocation"),
        ("misordered setup", "set up Go before every Go invocation"),
        ("unsupported version", "at least 1.25.0"),
        ("module caching enabled", "disable module caching"),
        ("mutable action ref", "full 40-hex SHA"),
        ("wrong Actionlint step identity", "Actionlint installation"),
    ],
    ids=[
        "missing",
        "misordered",
        "old-version",
        "cache",
        "sha-shape",
        "wrong-actionlint-step",
    ],
)
def test_parent_ci_go_contract_rejects_invalid_setup(
    scenario: str, expected_error: str
) -> None:
    """The shared Go contract catches missing or weakened setup requirements."""
    with pytest.raises(AssertionError, match=expected_error):
        assert_go_toolchain_contract(
            _synthetic_go_workflow(scenario),
            f"synthetic {scenario}",
            actionlint_step_name="Install CLI tools",
        )
