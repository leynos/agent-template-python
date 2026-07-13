"""Validate rendered project variants produced by the Copier template.

This module exercises the Python-only and Rust-extension template paths by
rendering temporary projects with ``pytest-copier`` and running the generated
quality gates.  The tests are intended for repository-level validation: they
verify generated files, Make targets, package imports, and Rust-specific output
without requiring callers to inspect the rendered project tree manually.

The tests create temporary projects, install generated dependencies through the
rendered ``make all`` target, and may download toolchain packages into the
normal user caches used by those generated projects.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture
from syrupy.assertion import SnapshotAssertion

from tests.helpers.generated_files import (
    parse_toml_file,
    parse_yaml_mapping,
    read_generated_text,
    require_mapping,
)
from tests.helpers.rendering import (
    check_generated_import,
    read_generated_file,
    render_project,
    run_quality_gates,
)
from tests.helpers.tooling_contracts import (
    assert_ci_coverage_action_contract,
    assert_common_make_targets,
    assert_generated_tooling_contracts,
)

MUTATION_WORKFLOW_PIN = "859416a90eb3987b46a57682c5d6b8964ad3f0a6"


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

    help_output = project.run("make help")
    for target in [
        "build",
        "check-fmt",
        "lint",
        "typecheck",
        "audit",
        "spelling",
        "test",
        "help",
    ]:
        assert f"  {target}" in help_output, (
            f"expected generated help output to list the {target!r} target"
        )
    assert help_output == snapshot


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

    pure_module = read_generated_file(project, f"{package_name}/pure.py")
    parsed_module = ast.parse(pure_module)
    hello_functions = [
        node
        for node in parsed_module.body
        if isinstance(node, ast.FunctionDef) and node.name == "hello"
    ]
    assert len(hello_functions) == 1, (
        "expected generated pure.py to define exactly one hello function"
    )
    hello_function = hello_functions[0]
    assert not hello_function.args.args, (
        "expected generated pure.py hello function to accept no positional arguments"
    )
    assert isinstance(hello_function.returns, ast.Name), (
        "expected generated pure.py hello function to declare a return annotation"
    )
    assert hello_function.returns.id == "str", (
        "expected generated pure.py hello function to return str"
    )
    assert pure_module == snapshot


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


def test_rust_template_make_test_runs_doctests(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Validate that Rust-enabled generated projects gate doctests.

    Parameters
    ----------
    copier : CopierFixture
        Fixture used to render the template into a temporary project.
    tmp_path : Path
        Temporary directory used as the generated project root.

    Returns
    -------
    None
        The test fails via assertions when the generated ``make test`` target
        does not run Rust documentation tests.

    Raises
    ------
    None
        Expected failures are captured through pytest assertions.

    Notes
    -----
    The test injects a deliberately broken Rust doctest and verifies that the
    generated project's public ``make test`` target reports the doctest
    failure.
    """
    proj = copier.copy(
        tmp_path / "rust-doctest",
        project_name="RustDoctest",
        package_name="rust_doctest_pkg",
        use_rust=True,
    )
    lib_rs = proj / "rust_extension" / "src" / "lib.rs"
    lib_rs.write_text(
        lib_rs.read_text(encoding="utf-8")
        + """

/// Deliberately broken doctest used by the parent template regression test.
///
/// ```
/// let status = std::process::ExitCode::SUCCESS;
/// assert!(status.success());
/// ```
pub fn doctest_regression_marker() {}
""",
        encoding="utf-8",
    )
    make = shutil.which("make")
    assert make is not None, "expected make to be available for generated tests"

    result = subprocess.run(
        [make, "test"],
        cwd=proj.path,
        check=False,
        capture_output=True,
        text=True,
    )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0, "expected make test to fail on broken doctests"
    assert "no method named `success`" in output, (
        "expected make test to compile doctests, exposing the broken example"
    )


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
    """Generated variants expose the expected Python and optional Rust tooling.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.
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
        The test passes when the generated tooling contracts are satisfied.
    """
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
    coverage_main_workflow = read_generated_text(
        project / ".github" / "workflows" / "coverage-main.yml"
    )
    act_validation_workflow = read_generated_text(
        project / ".github" / "workflows" / "act-validation.yml"
    )
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
        coverage_main_workflow=coverage_main_workflow,
        act_validation_workflow=act_validation_workflow,
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
    """Rendered workflows expose stable black-box inputs for act validation.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.
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
        The test passes when the generated CI coverage action contract matches
        the act validation expectations.
    """
    project = render_project(
        tmp_path / target_dir,
        copier,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
    )
    ci_workflow = read_generated_text(project / ".github" / "workflows" / "ci.yml")
    assert_ci_coverage_action_contract(
        ci_workflow=ci_workflow,
        package_name=package_name,
        use_rust=use_rust,
    )


@pytest.mark.parametrize(
    ("target_dir", "use_rust", "python_version", "expect_mutmut"),
    [
        ("mutation-312-pure", False, "3.12", False),
        ("mutation-312-rust", True, "3.12", False),
        ("mutation-313-pure", False, "3.13", True),
        ("mutation-314-rust", True, "3.14", True),
    ],
)
def test_generated_mutation_testing_gating(
    copier: CopierFixture,
    tmp_path: Path,
    target_dir: str,
    use_rust: bool,
    python_version: str,
    expect_mutmut: bool,
) -> None:
    """Rendered mutation testing follows the interpreter and Rust gates.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.
    target_dir
        Temporary project directory name for the rendered variant.
    use_rust
        Whether the rendered variant includes the optional Rust extension.
    python_version
        Minimum supported Python version answer passed to Copier.
    expect_mutmut
        Whether the baseline interpreter supports the mutmut workflow
        (3.13 or greater).

    Returns
    -------
    None
        The test passes when the mutmut job and ``[tool.mutmut]`` section
        render only for baselines of 3.13 or greater, the cargo-mutants job
        renders only with the Rust extension, and the workflow file is
        absent when both gates are off.
    """
    project = render_project(
        tmp_path / target_dir,
        copier,
        project_name="MutationProj",
        package_name="mutation_pkg",
        use_rust=use_rust,
        python_version=python_version,
    )
    pyproject = parse_toml_file(project / "pyproject.toml")
    mutmut_config = pyproject.get("tool", {}).get("mutmut")
    if expect_mutmut:
        assert mutmut_config == {
            "source_paths": ["mutation_pkg/"],
            "pytest_add_cli_args_test_selection": ["tests/"],
        }, "expected mutmut configuration for baselines of 3.13 or greater"
    else:
        assert mutmut_config is None, (
            "expected no mutmut configuration below a 3.13 baseline"
        )

    workflow_path = project / ".github" / "workflows" / "mutation-testing.yml"
    if not expect_mutmut and not use_rust:
        assert not workflow_path.exists(), (
            "expected no mutation workflow when both gates are off"
        )
        return
    workflow = parse_yaml_mapping(
        read_generated_text(workflow_path), "mutation workflow"
    )
    jobs = require_mapping(workflow, "jobs", "mutation workflow")
    assert ("mutation" in jobs) == expect_mutmut, (
        "expected the mutmut job only for baselines of 3.13 or greater"
    )
    assert ("mutation-rust" in jobs) == use_rust, (
        "expected the cargo-mutants job only for Rust variants"
    )
    if expect_mutmut:
        mutation_job = require_mapping(jobs, "mutation", "mutation workflow jobs")
        mutation_inputs = require_mapping(mutation_job, "with", "mutation job")
        assert mutation_inputs.get("python-version") == python_version, (
            "expected the mutmut job to run on the project's baseline Python"
        )
    for job_name, job in jobs.items():
        uses = str(job.get("uses", "")) if isinstance(job, dict) else ""
        assert uses.endswith(f"@{MUTATION_WORKFLOW_PIN}"), (
            f"expected {job_name} to pin the shared mutation workflow"
        )


@pytest.mark.parametrize("python_version", ["3", "three.13", "3.13.1", "4.0"])
def test_python_version_rejects_unexpected_formats(
    copier: CopierFixture,
    tmp_path: Path,
    python_version: str,
) -> None:
    """Reject malformed baseline versions at the Copier answer boundary.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project would be created.
    python_version
        Invalid version answer supplied to Copier.

    Returns
    -------
    None
        The test passes when Copier reports the version-format validation
        error before evaluating dependent template answers.
    """
    with pytest.raises(
        ValueError,
        match=r"Python version must use the 3\.X format",
    ):
        render_project(
            tmp_path / "invalid-python-version",
            copier,
            project_name="InvalidVersion",
            package_name="invalid_version",
            python_version=python_version,
        )
