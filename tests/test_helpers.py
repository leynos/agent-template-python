"""Validate direct helper-module error handling and edge cases.

The tests in this module exercise support helpers without rendering a full
Copier project.  They keep helper fallibility contracts explicit by checking
``pytest.fail`` conversion paths, generated-file schema helpers, and tooling
contract assertions directly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from tests.conftest import MINIMUM_ACT_VERSION, _parse_act_version
from tests.helpers.generated_files import (
    parse_toml_file,
    parse_yaml_mapping,
    read_generated_text,
    require_mapping,
    require_sequence,
)
from tests.helpers.rendering import read_generated_file
from tests.helpers.tooling_contracts import (
    assert_ci_coverage_action_contract,
    assert_common_make_targets,
    assert_coverage_main_workflow_contract,
)
from tests.utilities import docker_environment

if TYPE_CHECKING:
    from pytest_copier.plugin import CopierProject


REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("act version 0.2.84", (0, 2, 84)),
        ("act version v0.2.84", (0, 2, 84)),
    ],
)
def test_parse_act_version_accepts_supported_formats(
    output: str,
    expected: tuple[int, int, int],
) -> None:
    """Parse act version output used by the local preflight.

    Parameters
    ----------
    output
        Text emitted by ``act --version``.
    expected
        Semantic version tuple expected from the parser.

    Returns
    -------
    None
        The test passes when supported act version output formats parse to the
        expected tuple.
    """
    assert _parse_act_version(output) == expected, (
        f"expected act version parser to parse {output!r}"
    )


def test_parse_act_version_rejects_unexpected_output() -> None:
    """Reject act version output that does not contain a semantic version.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when unexpected output returns ``None`` so the preflight
        can skip optional act-backed tests with a clear reason.
    """
    assert _parse_act_version("unexpected act output") is None, (
        "expected act version parser to reject output without a semantic version"
    )


def test_old_act_version_is_below_minimum() -> None:
    """Compare stale act versions against the Node24-capable minimum.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when act ``0.2.80`` is detected as older than the
        minimum version required for Node24 action runtime support.
    """
    parsed_version = _parse_act_version("act version 0.2.80")

    assert parsed_version is not None, "expected parser to read stale act version"
    assert parsed_version < MINIMUM_ACT_VERSION, (
        "expected act 0.2.80 to be below the Node24-capable minimum"
    )


def test_docker_environment_removes_github_auth_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove host GitHub credentials from act subprocess environments.

    Parameters
    ----------
    monkeypatch
        Pytest fixture used to install representative host GitHub token
        variables.

    Returns
    -------
    None
        The test passes when ``docker_environment`` removes GitHub auth tokens
        so stale host credentials cannot break public action clones in ``act``.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "stale-token")
    monkeypatch.setenv("GH_TOKEN", "stale-token")

    env = docker_environment()

    assert "GITHUB_TOKEN" not in env, (
        "expected docker_environment to remove host GITHUB_TOKEN"
    )
    assert "GH_TOKEN" not in env, "expected docker_environment to remove host GH_TOKEN"


def test_read_generated_text_converts_os_errors(tmp_path: Path) -> None:
    """Convert generated-file read errors into pytest failures.

    Parameters
    ----------
    tmp_path
        Temporary directory used to build a missing file path for
        ``read_generated_text``.

    Returns
    -------
    None
        The test passes when ``read_generated_text`` raises
        ``pytest.fail.Exception`` with path context instead of propagating the
        raw ``FileNotFoundError`` from ``Path.read_text``.
    """
    missing_path = tmp_path / "nonexistent_generated.txt"

    with pytest.raises(pytest.fail.Exception, match="could not read generated file"):
        read_generated_text(missing_path)


def test_parse_toml_file_reports_decode_errors(tmp_path: Path) -> None:
    """Convert generated TOML decode errors into pytest failures.

    Parameters
    ----------
    tmp_path
        Temporary directory used to write invalid TOML content.

    Returns
    -------
    None
        The test passes when invalid TOML raises ``pytest.fail.Exception`` with
        generated-file context.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project\nname = 'broken'\n", encoding="utf-8")

    with pytest.raises(pytest.fail.Exception, match="could not parse generated TOML"):
        parse_toml_file(pyproject)


def test_parse_yaml_mapping_reports_invalid_yaml() -> None:
    """Convert generated YAML parser errors into pytest failures.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when invalid YAML raises ``pytest.fail.Exception`` with
        the supplied label.
    """
    with pytest.raises(pytest.fail.Exception, match="could not parse generated CI"):
        parse_yaml_mapping("jobs: [unterminated", "CI")


def test_parse_yaml_mapping_requires_mapping_root() -> None:
    """Reject generated YAML documents that do not parse to mappings.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when a sequence root raises ``pytest.fail.Exception``.
    """
    with pytest.raises(
        pytest.fail.Exception,
        match="expected generated CI workflow to parse as a mapping",
    ):
        parse_yaml_mapping("- lint\n- test\n", "CI workflow")


def test_generated_file_schema_helpers_require_expected_shapes() -> None:
    """Fail with schema-path context for wrong nested value shapes.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when mapping and sequence helpers accept valid values
        and fail on missing or incorrectly typed values.
    """
    mapping: dict[str, Any] = {
        "jobs": {"lint-test": {}},
        "steps": [{"name": "Check"}],
    }

    assert require_mapping(mapping, "jobs", "CI workflow") == {"lint-test": {}}, (
        "expected require_mapping(mapping, 'jobs', 'CI workflow') to return a "
        "jobs mapping containing lint-test"
    )
    assert require_sequence(mapping, "steps", "CI lint-test job") == [
        {"name": "Check"}
    ], (
        "expected require_sequence(mapping, 'steps', 'CI lint-test job') to "
        "return steps sequence [{'name': 'Check'}]"
    )

    with pytest.raises(
        pytest.fail.Exception,
        match="expected CI workflow to include mapping key 'jobs'",
    ):
        require_mapping({"jobs": []}, "jobs", "CI workflow")

    with pytest.raises(
        pytest.fail.Exception,
        match="expected CI lint-test job to include sequence key 'steps'",
    ):
        require_sequence({"steps": {}}, "steps", "CI lint-test job")


def test_read_generated_file_uses_shared_error_contract(tmp_path: Path) -> None:
    """Read rendered files through the shared generated-file helper contract.

    Parameters
    ----------
    tmp_path
        Temporary rendered-project stand-in used as the project root.

    Returns
    -------
    None
        The test passes when existing files are read and missing files raise
        ``pytest.fail.Exception`` instead of raw filesystem exceptions.
    """
    generated = tmp_path / "docs" / "users-guide.md"
    generated.parent.mkdir()
    generated.write_text("generated docs\n", encoding="utf-8")
    project = cast("CopierProject", tmp_path)

    assert read_generated_file(project, "docs/users-guide.md") == "generated docs\n", (
        "expected read_generated_file(project, 'docs/users-guide.md') to return "
        "the generated docs text"
    )
    with pytest.raises(pytest.fail.Exception, match="could not read generated file"):
        read_generated_file(project, "missing.md")


def test_common_make_targets_reports_missing_contracts() -> None:
    """Report missing shared Makefile targets through assertion messages.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when the shared target assertion accepts a complete
        Makefile fragment and rejects a fragment missing required targets.
    """
    assert_common_make_targets(
        "lint-python: build\n"
        "lint: lint-python\n"
        "audit: build\n"
        "TYPOS_VERSION ?= 1.48.0\n"
        "spelling:\n"
        "\tuv run scripts/generate_typos_config.py\n"
        "\tuv tool run typos --config typos.toml --force-exclude\n"
        "clean:\n"
        "\trm -rf .uv-cache .uv-tools\n"
    )

    with pytest.raises(AssertionError, match="Makefile should expose lint-python"):
        assert_common_make_targets("lint: lint-python\n")


def test_ci_coverage_action_contract_validates_pure_python_edges() -> None:
    """Validate pure-Python CI coverage action edge cases.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when a valid pure-Python workflow is accepted and a
        workflow with persistent checkout credentials is rejected.
    """
    assert_ci_coverage_action_contract(
        ci_workflow=_ci_workflow(
            persist_credentials="false",
            coverage_inputs="          artefact-name-suffix: helper-pkg\n",
        ),
        package_name="helper_pkg",
        use_rust=False,
    )

    with pytest.raises(
        AssertionError,
        match="expected CI checkout steps to disable credential persistence",
    ):
        assert_ci_coverage_action_contract(
            ci_workflow=_ci_workflow(
                persist_credentials="true",
                coverage_inputs="          artefact-name-suffix: helper-pkg\n",
            ),
            package_name="helper_pkg",
            use_rust=False,
        )


def test_ci_coverage_action_contract_validates_rust_manifest_edge() -> None:
    """Validate Rust CI coverage action cargo-manifest requirements.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when the Rust workflow requires the extension
        ``cargo-manifest`` input on the shared coverage action.
    """
    with pytest.raises(
        AssertionError,
        match="expected Rust variant to pass the extension manifest to coverage",
    ):
        assert_ci_coverage_action_contract(
            ci_workflow=_ci_workflow(
                persist_credentials="false",
                coverage_inputs="          artefact-name-suffix: helper-pkg\n",
            ),
            package_name="helper_pkg",
            use_rust=True,
        )

    assert_ci_coverage_action_contract(
        ci_workflow=_ci_workflow(
            persist_credentials="false",
            coverage_inputs=(
                "          artefact-name-suffix: helper-pkg\n"
                "          cargo-manifest: rust_extension/Cargo.toml\n"
            ),
        ),
        package_name="helper_pkg",
        use_rust=True,
    )


def test_ci_coverage_action_contract_accepts_any_pinned_sha_rejects_branch_ref() -> (
    None
):
    """Validate the coverage action contract is SHA-value-agnostic but shape-strict.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when a workflow pinned to a different 40-hex commit
        SHA is accepted (Dependabot owns the SHA value) and a workflow
        pinned to a mutable branch ref is rejected.
    """
    workflow = _ci_workflow(
        persist_credentials="false",
        coverage_inputs="          artefact-name-suffix: helper-pkg\n",
    )

    dependabot_bumped_workflow = workflow.replace(
        "927edd45ae77be4251a8a18ca9eb5613a2e32cbd",
        "0123456789abcdef0123456789abcdef01234567",
    )
    assert_ci_coverage_action_contract(
        ci_workflow=dependabot_bumped_workflow,
        package_name="helper_pkg",
        use_rust=False,
    )

    branch_ref_workflow = workflow.replace(
        "@927edd45ae77be4251a8a18ca9eb5613a2e32cbd", "@main"
    )
    with pytest.raises(
        AssertionError,
        match="expected CI to use the shared coverage action pinned to a 40-hex",
    ):
        assert_ci_coverage_action_contract(
            ci_workflow=branch_ref_workflow,
            package_name="helper_pkg",
            use_rust=False,
        )


def test_parent_makefile_help_target_lists_available_targets() -> None:
    """Validate the parent repository ``help`` target output.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when ``make help`` advertises the parent ``help`` and
        quality-gate targets.
    """
    result = subprocess.run(
        ["make", "help"],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        encoding="utf-8",
    )

    assert "Available targets:" in result.stdout, (
        "expected parent Makefile help target to print an available-targets header"
    )
    assert "help" in result.stdout, (
        "expected parent Makefile help target to list the help target"
    )
    for target in ["check-fmt", "lint", "typecheck", "test"]:
        assert target in result.stdout, (
            f"expected parent Makefile help target to list the {target} target"
        )


def test_parent_makefile_test_target_uses_requisite_pytest_command() -> None:
    """Validate the parent repository ``test`` target command contract.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when the parent Makefile exposes ``test`` as phony,
        checks for ``uvx``, and runs pytest through the resolved executable with
        the required template-test packages.
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert ".PHONY: help check-fmt lint spelling test typecheck" in makefile, (
        "expected parent Makefile to mark documented gate targets as phony"
    )
    assert "check-fmt: ## Verify template test formatting" in makefile, (
        "expected parent Makefile to expose a documented check-fmt target"
    )
    assert "$(UV) ruff format --check tests/" in makefile, (
        "expected parent Makefile check-fmt target to run Ruff formatting checks"
    )
    assert "lint: ## Run template test lint checks" in makefile, (
        "expected parent Makefile to expose a documented lint target"
    )
    assert "$(UV) ruff check tests/" in makefile, (
        "expected parent Makefile lint target to run Ruff checks"
    )
    assert "$(UV) --with interrogate interrogate --fail-under 100 tests/" in makefile, (
        "expected parent Makefile lint target to enforce docstring coverage"
    )
    assert "typecheck: ## Run template test type checks" in makefile, (
        "expected parent Makefile to expose a documented typecheck target"
    )
    assert (
        "$(UV) --with hypothesis --with pytest --with pytest-copier --with pyyaml --with syrupy "
        "--with make-parser ty check tests/" in makefile
    ), "expected parent Makefile typecheck target to run ty with test dependencies"
    assert "test: ## Run template tests" in makefile, (
        "expected parent Makefile to expose a documented test target"
    )
    assert "UV := $(shell command -v uvx 2>/dev/null)" in makefile, (
        "expected parent Makefile to resolve uvx before running tests"
    )
    assert "uvx is required to run template tests" in makefile, (
        "expected parent Makefile to fail early with a uvx installation message"
    )
    assert "WITH_ACT ?= 0" in makefile, (
        "expected parent Makefile to default act validation off"
    )
    assert "RUN_ACT_VALIDATION=1" in makefile, (
        "expected parent Makefile to map WITH_ACT to act validation"
    )
    assert (
        "$(ACT_TEST_ENV) $(UV) --with hypothesis --with pytest-copier --with pyyaml --with syrupy "
        "--with make-parser pytest tests/" in makefile
    ), (
        "expected parent Makefile test target to run pytest through $(UV) with "
        "Hypothesis, pytest-copier, pyyaml, syrupy, make-parser, and act environment wiring"
    )


def _coverage_main_workflow(*, guard: str, rust_setup: str = "") -> str:
    """Return a minimal generated coverage-main workflow for contract tests."""
    return f"""\
name: Coverage (main)
on:
  push:
    branches: [main]
  workflow_dispatch:
jobs:
  coverage-upload:
    permissions:
      contents: read
    steps:
{rust_setup}\
      - name: Generate coverage
        uses: leynos/shared-actions/.github/actions/generate-coverage@927edd45ae77be4251a8a18ca9eb5613a2e32cbd
        with:
          output-path: coverage.xml
          format: cobertura
          artefact-name-suffix: helper-pkg
          with-ratchet: 'true'
      - name: Upload coverage data to CodeScene
        if: {guard}
        uses: leynos/shared-actions/.github/actions/upload-codescene-coverage@927edd45ae77be4251a8a18ca9eb5613a2e32cbd
        with:
          format: cobertura
          path: coverage.xml
"""


def test_coverage_main_workflow_contract_validates_guarded_upload() -> None:
    """Validate the push-to-main coverage upload workflow contract.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when a guarded pure-Python coverage-main workflow is
        accepted and an unguarded upload is rejected.
    """
    assert_coverage_main_workflow_contract(
        coverage_main_workflow=_coverage_main_workflow(
            guard="env.CS_ACCESS_TOKEN != ''"
        ),
        package_name="helper_pkg",
        use_rust=False,
    )

    with pytest.raises(
        AssertionError,
        match="expected the CodeScene upload to skip when the access token is absent",
    ):
        assert_coverage_main_workflow_contract(
            coverage_main_workflow=_coverage_main_workflow(guard="always()"),
            package_name="helper_pkg",
            use_rust=False,
        )


def test_coverage_main_workflow_contract_requires_rust_setup() -> None:
    """Validate the Rust variant coverage-main workflow contract.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when a Rust coverage-main workflow that omits Rust
        setup and the extension manifest is rejected.
    """
    with pytest.raises(
        AssertionError,
        match="expected Rust variant coverage-main to pass the extension manifest",
    ):
        assert_coverage_main_workflow_contract(
            coverage_main_workflow=_coverage_main_workflow(
                guard="env.CS_ACCESS_TOKEN != ''"
            ),
            package_name="helper_pkg",
            use_rust=True,
        )

    rust_setup = (
        "      - name: Set up Rust\n"
        "        uses: leynos/shared-actions/.github/actions/setup-rust"
        "@927edd45ae77be4251a8a18ca9eb5613a2e32cbd\n"
    )
    rust_manifest = "          cargo-manifest: rust_extension/Cargo.toml\n"
    workflow = _coverage_main_workflow(
        guard="env.CS_ACCESS_TOKEN != ''", rust_setup=rust_setup
    ).replace(
        "          with-ratchet: 'true'\n",
        "          with-ratchet: 'true'\n" + rust_manifest,
    )
    assert_coverage_main_workflow_contract(
        coverage_main_workflow=workflow,
        package_name="helper_pkg",
        use_rust=True,
    )


def test_coverage_main_workflow_contract_accepts_any_pinned_sha_rejects_branch_ref() -> (
    None
):
    """Validate the coverage-main contract is SHA-value-agnostic but shape-strict.

    Parameters
    ----------
    None
        This test does not use pytest fixtures.

    Returns
    -------
    None
        The test passes when a coverage-main workflow pinned to a different
        40-hex commit SHA is accepted (Dependabot owns the SHA value) and a
        workflow pinned to a mutable branch ref is rejected.
    """
    workflow = _coverage_main_workflow(guard="env.CS_ACCESS_TOKEN != ''")

    dependabot_bumped_workflow = workflow.replace(
        "927edd45ae77be4251a8a18ca9eb5613a2e32cbd",
        "0123456789abcdef0123456789abcdef01234567",
    )
    assert_coverage_main_workflow_contract(
        coverage_main_workflow=dependabot_bumped_workflow,
        package_name="helper_pkg",
        use_rust=False,
    )

    branch_ref_workflow = workflow.replace(
        "generate-coverage@927edd45ae77be4251a8a18ca9eb5613a2e32cbd",
        "generate-coverage@main",
    )
    with pytest.raises(
        AssertionError,
        match="expected coverage-main to use the shared coverage action pinned "
        "to a 40-hex",
    ):
        assert_coverage_main_workflow_contract(
            coverage_main_workflow=branch_ref_workflow,
            package_name="helper_pkg",
            use_rust=False,
        )

    upload_branch_ref_workflow = workflow.replace(
        "upload-codescene-coverage@927edd45ae77be4251a8a18ca9eb5613a2e32cbd",
        "upload-codescene-coverage@main",
    )
    with pytest.raises(
        AssertionError,
        match="expected coverage-main to use the shared upload action pinned "
        "to a 40-hex",
    ):
        assert_coverage_main_workflow_contract(
            coverage_main_workflow=upload_branch_ref_workflow,
            package_name="helper_pkg",
            use_rust=False,
        )


def _ci_workflow(*, persist_credentials: str, coverage_inputs: str) -> str:
    """Return a minimal generated CI workflow for coverage-contract tests."""
    return f"""\
name: CI
jobs:
  lint-test:
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: {persist_credentials}
      - name: Test and Measure Coverage
        if: ${{{{ github.event_name == 'pull_request' }}}}
        uses: leynos/shared-actions/.github/actions/generate-coverage@927edd45ae77be4251a8a18ca9eb5613a2e32cbd
        with:
          output-path: coverage.xml
          format: cobertura
          with-ratchet: 'true'
{coverage_inputs}\
"""
