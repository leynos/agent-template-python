"""Validate rendered project variants produced by the Copier template.

This module exercises the Python-only and Rust-extension template paths by
rendering temporary projects with ``pytest-copier`` and running the generated
quality gates.  The tests are intended for repository-level validation: they
verify generated files, Make targets, package imports, and Rust-specific output
without requiring callers to inspect the rendered project tree manually.

Typical usage is to run this module through pytest after changing template
files, generated Makefile targets, or package layout:

Examples
--------
Run the generated-template checks directly::

    python -m pytest tests/test_template.py -v

The tests create temporary projects, install generated dependencies through the
rendered ``make all`` target, and may download toolchain packages into the
normal user caches used by those generated projects.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture
from syrupy.assertion import SnapshotAssertion

from tests.helpers.generated_files import (
    parse_toml_file,
    parse_yaml_mapping,
    read_generated_text,
    require_mapping,
    require_sequence,
)
from tests.helpers.rendering import (
    check_generated_import,
    read_generated_file,
    render_project,
    run_quality_gates,
)
from tests.helpers.tooling_contracts import (
    assert_common_make_targets,
    assert_generated_tooling_contracts,
    checkout_steps_disable_credentials,
)


def test_python_only_help_output_snapshot(
    copier: CopierFixture, tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """Validate the generated Python-only help output.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.
    snapshot
        Syrupy snapshot assertion fixture for stable parent-repository output
        checks.

    Returns
    -------
    None
        The test passes when ``make help`` matches the stored snapshot.

    Raises
    ------
    AssertionError
        Raised when generated help output differs from the stored snapshot.

    Examples
    --------
    Refresh the help-output snapshot after intentional Makefile help changes::

        python -m pytest \
          tests/test_template.py::test_python_only_help_output_snapshot \
          --snapshot-update
    """
    project = copier.copy(
        tmp_path / "help",
        project_name="Help",
        package_name="help_pkg",
        use_rust=False,
    )

    assert project.run("make help") == snapshot


@pytest.mark.parametrize(
    ("target_dir", "project_name", "package_name", "use_rust"),
    [
        ("pure-module", "PureModule", "pure_module_pkg", False),
        ("rust-module", "RustModule", "rust_module_pkg", True),
    ],
)
def test_pure_module_snapshot(
    copier: CopierFixture,
    tmp_path: Path,
    snapshot: SnapshotAssertion,
    target_dir: str,
    project_name: str,
    package_name: str,
    use_rust: bool,
) -> None:
    """Validate the rendered pure implementation module formatting.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.
    snapshot
        Syrupy snapshot assertion fixture for stable generated file contents.
    target_dir
        Temporary project directory name for the rendered variant.
    project_name
        Project name answer passed to Copier.
    package_name
        Package name answer passed to Copier.
    use_rust
        Whether the rendered variant includes the optional Rust extension.

    Returns
    -------
    None
        The test passes when the generated pure module matches the snapshot.
    """
    project = copier.copy(
        tmp_path / target_dir,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
    )

    assert read_generated_file(project, f"{package_name}/pure.py") == snapshot


def test_python_only_template(copier: CopierFixture, tmp_path: Path) -> None:
    """Validate the Python-only rendered project variant.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.

    Returns
    -------
    None
        The test passes after the Python-only quality gates, file assertions,
        Makefile assertions, and import check all succeed.

    Examples
    --------
    Run only the Python-only variant check::

        python -m pytest tests/test_template.py::test_python_only_template -v
    """
    proj = copier.copy(
        tmp_path / "pure", project_name="Pure", package_name="pure_pkg", use_rust=False
    )
    run_quality_gates(proj)

    assert not (proj / "rust_extension").exists(), (
        "rust_extension directory should not exist for Python-only template"
    )
    assert not (proj / "docs" / "rust-extension.md").exists(), (
        "Rust documentation should not be generated for Python-only template"
    )
    assert "maturin" not in (proj / "pyproject.toml").read_text(encoding="utf-8"), (
        "maturin should not be in pyproject.toml for Python-only template"
    )
    makefile = read_generated_file(proj, "Makefile")
    assert_common_make_targets(makefile)
    assert "lint-rust" not in makefile, (
        "Python-only Makefile should not expose lint-rust"
    )

    check_generated_import(proj, "pure_pkg", "hello from Python")


def test_rust_template(copier: CopierFixture, tmp_path: Path) -> None:
    """Validate the default Rust-extension rendered project variant.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.

    Returns
    -------
    None
        The test passes after Rust-enabled quality gates, generated file
        assertions, Makefile assertions, and import checks all succeed.

    Examples
    --------
    Run only the Rust-enabled variant check::

        python -m pytest tests/test_template.py::test_rust_template -v
    """
    proj = copier.copy(
        tmp_path / "rust",
        project_name="RustProj",
        package_name="rust_pkg",
        use_rust=True,
    )
    run_quality_gates(proj)

    assert (proj / "rust_extension").exists(), (
        "rust_extension directory should exist for Rust template"
    )
    assert (proj / "docs" / "rust-extension.md").exists(), (
        "Rust documentation should be generated for Rust template"
    )
    assert "maturin" in (proj / "pyproject.toml").read_text(encoding="utf-8"), (
        "maturin should be in pyproject.toml for Rust template"
    )
    makefile = read_generated_file(proj, "Makefile")
    assert_common_make_targets(makefile)
    assert "lint-rust: build whitaker" in makefile, (
        "Rust Makefile should expose lint-rust"
    )
    assert "cargo is required for Rust tests" in makefile, (
        "Rust Makefile should fail clearly when cargo is unavailable"
    )

    check_generated_import(proj, "rust_pkg", "hello from Rust")


def test_rust_template_custom_package(copier: CopierFixture, tmp_path: Path) -> None:
    """Ensure templating uses the provided package name.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.

    Returns
    -------
    None
        The test passes after quality gates, file assertions, and import checks
        all succeed.

    Examples
    --------
    Run this case directly while debugging package-name rendering::

        python -m pytest tests/test_template.py::test_rust_template_custom_package -v
    """
    proj = copier.copy(
        tmp_path / "rust_custom",
        project_name="RustProj",
        package_name="custom_pkg",
        use_rust=True,
    )
    run_quality_gates(proj)

    assert (proj / "rust_extension").exists(), (
        "rust_extension directory should exist for custom package Rust template"
    )
    text = (proj / "pyproject.toml").read_text(encoding="utf-8")
    assert "custom_pkg" in text, "custom package name should appear in pyproject.toml"

    check_generated_import(proj, "custom_pkg", "hello from Rust")


@pytest.mark.parametrize(
    ("target_dir", "project_name", "package_name", "use_rust"),
    [
        ("tooling-pure", "ToolingPure", "tooling_pure", False),
        ("tooling-rust", "ToolingRust", "tooling_rust", True),
    ],
)
def test_generated_tooling_contracts(
    copier: CopierFixture,
    tmp_path: Path,
    target_dir: str,
    project_name: str,
    package_name: str,
    use_rust: bool,
) -> None:
    """Generated variants expose the expected Python and optional Rust tooling."""
    project = render_project(
        tmp_path / target_dir,
        copier,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
    )

    run_quality_gates(project)
    project.run("uv tool run mbake validate Makefile")

    pyproject = parse_toml_file(project / "pyproject.toml")
    agents = read_generated_text(project / "AGENTS.md")
    makefile = read_generated_text(project / "Makefile")
    ci_workflow = read_generated_text(project / ".github" / "workflows" / "ci.yml")
    release_workflow = read_generated_text(
        project / ".github" / "workflows" / "release.yml"
    )
    build_wheels_workflow = read_generated_text(
        project / ".github" / "workflows" / "build-wheels.yml"
    )
    build_wheels_action = read_generated_text(
        project / ".github" / "actions" / "build-wheels" / "action.yml"
    )
    pure_wheel_action = read_generated_text(
        project / ".github" / "actions" / "pure-python-wheel" / "action.yml"
    )

    assert_generated_tooling_contracts(
        package_name=package_name,
        agents=agents,
        pyproject=pyproject,
        makefile=makefile,
        ci_workflow=ci_workflow,
        release_workflow=release_workflow,
        build_wheels_workflow=build_wheels_workflow,
        build_wheels_action=build_wheels_action,
        pure_wheel_action=pure_wheel_action,
        use_rust=use_rust,
    )


@pytest.mark.parametrize(
    ("target_dir", "project_name", "package_name", "use_rust"),
    [
        ("workflow-pure", "WorkflowPure", "workflow_pure", False),
        ("workflow-rust", "WorkflowRust", "workflow_rust", True),
    ],
)
def test_generated_github_workflows_match_act_validation_contract(
    copier: CopierFixture,
    tmp_path: Path,
    target_dir: str,
    project_name: str,
    package_name: str,
    use_rust: bool,
) -> None:
    """Rendered workflows expose stable black-box inputs for act validation."""
    project = render_project(
        tmp_path / target_dir,
        copier,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
    )
    ci_workflow = read_generated_text(project / ".github" / "workflows" / "ci.yml")
    parsed_ci_workflow = parse_yaml_mapping(ci_workflow, "CI workflow")
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    lint_test = require_mapping(jobs, "lint-test", "CI workflow jobs")
    steps = require_sequence(lint_test, "steps", "CI lint-test job")

    assert checkout_steps_disable_credentials(steps), (
        "expected CI checkout steps to disable credential persistence"
    )
    coverage_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Test and Measure Coverage"
    ]
    assert len(coverage_steps) == 1, "expected one shared coverage action step"
    coverage_step = coverage_steps[0]
    assert (
        coverage_step.get("uses")
        == "leynos/shared-actions/.github/actions/generate-coverage"
        "@d400b079fb6a8fa92f7e7b6c57f3d1c92a4b2d54"
    ), "expected CI to use the pinned shared coverage action"
    coverage_inputs = require_mapping(coverage_step, "with", "coverage step")
    assert coverage_inputs.get("output-path") == "coverage.xml", (
        "expected CI coverage output path to match the act assertion"
    )
    assert coverage_inputs.get("format") == "cobertura", (
        "expected CI coverage format to match the CodeScene upload"
    )
    assert coverage_inputs.get("artefact-name-suffix") == package_name.replace(
        "_", "-"
    ), "expected package-specific coverage artefact name suffix"
    if use_rust:
        assert coverage_inputs.get("cargo-manifest") == "rust_extension/Cargo.toml", (
            "expected Rust variant to pass the extension manifest to coverage"
        )
    else:
        assert "cargo-manifest" not in coverage_inputs, (
            "expected pure-Python variant to omit Rust coverage inputs"
        )
