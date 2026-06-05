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
)

if TYPE_CHECKING:
    from pytest_copier.plugin import CopierProject


REPO_ROOT = Path(__file__).resolve().parent.parent


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

    assert ".PHONY: help check-fmt lint test typecheck" in makefile, (
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
    assert "typecheck: ## Run template test type checks" in makefile, (
        "expected parent Makefile to expose a documented typecheck target"
    )
    assert (
        "$(UV) --with pytest --with pytest-copier --with pyyaml --with syrupy "
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
        "$(ACT_TEST_ENV) $(UV) --with pytest-copier --with pyyaml --with syrupy "
        "--with make-parser pytest tests/" in makefile
    ), (
        "expected parent Makefile test target to run pytest through $(UV) with "
        "pytest-copier, pyyaml, syrupy, make-parser, and act environment wiring"
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
        uses: leynos/shared-actions/.github/actions/generate-coverage@455d9ed03477c0026da96c2541ca26569a74acac
        with:
          output-path: coverage.xml
          format: cobertura
{coverage_inputs}\
"""
