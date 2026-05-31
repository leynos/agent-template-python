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

import shlex
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from pytest_copier.plugin import CopierFixture, CopierProject
from syrupy.assertion import SnapshotAssertion


def run_quality_gates(project: CopierProject) -> None:
    """Run the rendered project's public quality gate.

    Parameters
    ----------
    project
        Rendered ``pytest-copier`` project whose root contains the generated
        Makefile.

    Returns
    -------
    None
        The helper delegates validation to the generated project's ``make all``
        target.

    Raises
    ------
    AssertionError
        Raised by ``pytest-copier`` if the command exits unsuccessfully.

    Examples
    --------
    Validate a rendered project before making assertions about its files::

        project = copier.copy(tmp_path / "pure", use_rust=False)
        run_quality_gates(project)
    """
    project.run("make all")


def render_project(
    tmp_path: Path,
    copier: CopierFixture,
    *,
    project_name: str,
    package_name: str,
    use_rust: bool = False,
    python_version: str = "3.10",
) -> CopierProject:
    """Render a generated Python project with explicit template answers.

    Parameters
    ----------
    tmp_path
        Temporary directory used as the generated project destination.
    copier
        ``pytest-copier`` fixture bound to this template repository.
    project_name
        Project name answer passed to Copier.
    package_name
        Package name answer passed to Copier.
    use_rust
        Whether to include the optional PyO3 extension.
    python_version
        Minimum supported Python version answer passed to Copier.

    Returns
    -------
    CopierProject
        Rendered project wrapper for file assertions and command execution.
    """
    return copier.copy(
        tmp_path,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
        python_version=python_version,
    )


def check_generated_import(project: CopierProject, package: str, greeting: str) -> None:
    """Import a generated package and assert its greeting.

    Parameters
    ----------
    project
        Rendered project whose managed environment should contain the package.
    package
        Import name to load through ``importlib.import_module``.
    greeting
        Expected return value from the generated package's ``hello`` function.

    Returns
    -------
    None
        The helper succeeds when the generated import and assertion succeed.

    Raises
    ------
    AssertionError
        Raised by ``pytest-copier`` if the command exits unsuccessfully.

    Examples
    --------
    Check the generated pure-Python package import path::

        check_generated_import(project, "pure_pkg", "hello from Python")
    """
    script = (
        "import importlib; "
        f"module = importlib.import_module({package!r}); "
        f"assert module.hello() == {greeting!r}"
    )
    project.run(f"uv run python -c {shlex.quote(script)}")


def read_generated_file(project: CopierProject, relative_path: str) -> str:
    """Read a rendered project file as UTF-8 text.

    Parameters
    ----------
    project
        Rendered ``pytest-copier`` project to read from.
    relative_path
        Path to the generated file, relative to the rendered project root.

    Returns
    -------
    str
        File contents decoded as UTF-8.

    Raises
    ------
    FileNotFoundError
        Raised if the requested generated file does not exist.

    Examples
    --------
    Read the generated Makefile for target assertions::

        makefile = read_generated_file(project, "Makefile")
    """
    return (project / relative_path).read_text(encoding="utf-8")


def read_generated_text(path: Path) -> str:
    """Read a generated file with assertion-focused error context."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        pytest.fail(f"could not read generated file {path}: {error}")


def parse_toml_file(path: Path) -> dict[str, Any]:
    """Parse generated TOML with assertion-focused error context."""
    text = read_generated_text(path)
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        pytest.fail(f"could not parse generated TOML {path}: {error}")
    return parsed


def parse_yaml_mapping(text: str, label: str) -> dict[str, Any]:
    """Parse generated YAML as a mapping with clear failure context."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as error:
        pytest.fail(f"could not parse generated {label}: {error}")
    if not isinstance(parsed, dict):
        pytest.fail(f"expected generated {label} to parse as a mapping")
    return parsed


def require_mapping(mapping: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    """Return a nested mapping or fail with the missing schema path."""
    value = mapping.get(key)
    if not isinstance(value, dict):
        pytest.fail(f"expected {label} to include mapping key {key!r}")
    return value


def require_sequence(mapping: dict[str, Any], key: str, label: str) -> list[Any]:
    """Return a nested sequence or fail with the missing schema path."""
    value = mapping.get(key)
    if not isinstance(value, list):
        pytest.fail(f"expected {label} to include sequence key {key!r}")
    return value


def assert_common_make_targets(makefile: str) -> None:
    """Assert Makefile targets shared by all generated variants.

    Parameters
    ----------
    makefile
        UTF-8 text of a generated Makefile.

    Returns
    -------
    None
        The helper returns after all common target assertions pass.

    Raises
    ------
    AssertionError
        Raised when a required shared target or cleanup path is missing.

    Examples
    --------
    Validate shared targets after reading a generated Makefile::

        assert_common_make_targets(makefile)
    """
    assert "lint-python: build" in makefile, "Makefile should expose lint-python"
    assert "lint: lint-python" in makefile, "lint should delegate to lint-python"
    assert ".uv-cache .uv-tools" in makefile, "clean should remove uv state dirs"


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


def assert_generated_tooling_contracts(
    *,
    package_name: str,
    agents: str,
    pyproject: dict[str, Any],
    makefile: str,
    ci_workflow: str,
    release_workflow: str,
    build_wheels_workflow: str,
    build_wheels_action: str,
    pure_wheel_action: str,
    use_rust: bool,
) -> None:
    """Assert generated Python/Rust tooling contracts from one validator."""
    assert_pyproject_contracts(
        package_name=package_name,
        pyproject=pyproject,
        use_rust=use_rust,
    )
    assert_agents_contracts(agents)
    assert_makefile_contracts(makefile=makefile, use_rust=use_rust)
    assert_ci_workflow_contracts(ci_workflow=ci_workflow, use_rust=use_rust)
    assert_release_workflow_contracts(
        release_workflow=release_workflow,
        use_rust=use_rust,
    )
    assert_wheel_workflow_contracts(
        build_wheels_workflow=build_wheels_workflow,
        build_wheels_action=build_wheels_action,
        pure_wheel_action=pure_wheel_action,
    )


def assert_pyproject_contracts(
    *, package_name: str, pyproject: dict[str, Any], use_rust: bool
) -> None:
    """Assert generated Python packaging contracts."""
    project = require_mapping(pyproject, "project", "pyproject.toml")
    assert project.get("name"), "expected generated project metadata to include a name"
    assert project.get("requires-python") == ">=3.10", (
        "expected generated pyproject.toml to use the requested Python version"
    )
    dependency_groups = require_mapping(
        pyproject,
        "dependency-groups",
        "pyproject.toml",
    )
    dev_dependencies = dependency_groups.get("dev")
    assert isinstance(dev_dependencies, list), (
        "expected generated pyproject.toml to include a dev dependency group"
    )
    for dependency in ["pytest", "ruff", "pyright", "ty", "pytest-xdist"]:
        assert dependency in dev_dependencies, (
            f"expected generated dev dependencies to include {dependency}"
        )

    build_system = require_mapping(pyproject, "build-system", "pyproject.toml")
    if use_rust:
        assert build_system.get("build-backend") == "maturin", (
            "expected Rust variant to use maturin as the build backend"
        )
        maturin = require_mapping(pyproject, "tool", "pyproject.toml").get("maturin")
        assert isinstance(maturin, dict), (
            "expected Rust variant to include tool.maturin configuration"
        )
        assert maturin.get("manifest-path") == "rust_extension/Cargo.toml", (
            "expected Rust variant to point maturin at the extension manifest"
        )
        assert maturin.get("module-name") == f"{package_name}._{package_name}_rs", (
            "expected Rust variant to render the package-specific module name"
        )
    else:
        assert build_system.get("build-backend") == "hatchling.build", (
            "expected pure-Python variant to use hatchling as the build backend"
        )
        assert "maturin" not in pyproject.get("tool", {}), (
            "expected pure-Python variant to omit maturin configuration"
        )


def assert_agents_contracts(agents: str) -> None:
    """Assert generated assistant guidance documents act-enabled testing."""
    assert "make test WITH_ACT=1" in agents, (
        "expected generated AGENTS.md to document act-enabled test runs"
    )
    assert "RUN_ACT_VALIDATION=1" in agents, (
        "expected generated AGENTS.md to describe the pytest act environment"
    )


def assert_makefile_contracts(*, makefile: str, use_rust: bool) -> None:
    """Assert generated Makefile contracts for both template variants."""
    assert_common_make_targets(makefile)
    assert "WITH_ACT ?= 0" in makefile, (
        "expected generated Makefile to default act validation off"
    )
    assert "ACT_TEST_ENV =" in makefile, (
        "expected generated Makefile to map WITH_ACT to pytest environment"
    )
    assert "RUN_ACT_VALIDATION=1" in makefile, (
        "expected generated Makefile to enable act validation for pytest"
    )
    assert "$(UV_ENV) $(ACT_TEST_ENV) $(UV) run pytest" in makefile, (
        "expected generated test target to include the act test environment"
    )
    assert "PYTHON_TARGETS ?=" in makefile, (
        "expected generated Makefile to define Python target selection"
    )
    assert "PYLINT_PYPY_SHIM_REF ?=" in makefile, (
        "expected generated Makefile to expose the Pylint shim revision"
    )
    assert "test: build $(VENV_TOOLS)" in makefile, (
        "expected generated Makefile test target to depend on the project env"
    )
    if use_rust:
        assert "TEST_CMD :=" in makefile, (
            "expected Rust variant to select nextest or cargo test"
        )
        assert "lint-rust: build whitaker" in makefile, (
            "expected Rust variant to expose the Rust lint target"
        )
        assert "cargo is required for Rust tests" in makefile, (
            "expected Rust variant to fail clearly without cargo"
        )
        assert "$(CARGO) $(TEST_CMD) $(TEST_FLAGS)" in makefile, (
            "expected Rust variant tests to use the selected cargo test command"
        )
    else:
        assert "lint-rust" not in makefile, (
            "expected pure-Python variant to omit Rust lint targets"
        )
        assert "TEST_CMD :=" not in makefile, (
            "expected pure-Python variant to omit Rust test command selection"
        )


def assert_ci_workflow_contracts(*, ci_workflow: str, use_rust: bool) -> None:
    """Assert generated CI workflow contracts."""
    parsed_ci_workflow = parse_yaml_mapping(ci_workflow, "CI workflow")
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    lint_test = require_mapping(jobs, "lint-test", "CI workflow jobs")
    steps = require_sequence(lint_test, "steps", "CI lint-test job")
    assert checkout_steps_disable_credentials(steps), (
        "expected generated CI workflow to disable checkout credentials"
    )
    assert "make check-fmt" in ci_workflow, (
        "expected generated CI workflow to run the formatting gate"
    )
    assert "make lint" in ci_workflow, (
        "expected generated CI workflow to run the lint gate"
    )
    assert "make typecheck" in ci_workflow, (
        "expected generated CI workflow to run the typecheck gate"
    )
    assert "make build" in ci_workflow, (
        "expected generated CI workflow to build the project before checks"
    )
    assert "leynos/shared-actions/.github/actions/generate-coverage" in ci_workflow, (
        "expected generated CI workflow to use the shared coverage action"
    )
    if use_rust:
        assert "leynos/shared-actions/.github/actions/setup-rust" in ci_workflow, (
            "expected Rust variant CI to set up Rust"
        )
        assert "Cache Rust lint and test tools" in ci_workflow, (
            "expected Rust variant CI to cache Rust tools"
        )
        assert "cargo-manifest: rust_extension/Cargo.toml" in ci_workflow, (
            "expected Rust variant CI to pass the Rust manifest to coverage"
        )
    else:
        assert "setup-rust" not in ci_workflow, (
            "expected pure-Python CI to omit Rust setup"
        )
        assert "cargo-manifest" not in ci_workflow, (
            "expected pure-Python CI to omit Rust coverage inputs"
        )


def assert_release_workflow_contracts(*, release_workflow: str, use_rust: bool) -> None:
    """Assert generated release workflow contracts."""
    parsed_release_workflow = parse_yaml_mapping(release_workflow, "release workflow")
    jobs = require_mapping(parsed_release_workflow, "jobs", "release workflow")
    release = require_mapping(jobs, "release", "release workflow jobs")
    release_steps = require_sequence(release, "steps", "release job")
    assert checkout_steps_disable_credentials(release_steps), (
        "expected generated release workflow to disable checkout credentials"
    )
    assert "softprops/action-gh-release@v2" in release_workflow, (
        "expected release workflow to create a GitHub release"
    )
    assert "actions/download-artifact@v4" in release_workflow, (
        "expected release workflow to download wheel artefacts"
    )
    if use_rust:
        assert "build-wheels" in jobs, (
            "expected Rust variant release workflow to build platform wheels"
        )
        build_wheels = require_mapping(jobs, "build-wheels", "release workflow jobs")
        assert build_wheels.get("uses") == "./.github/workflows/build-wheels.yml", (
            "expected Rust variant release workflow to call build-wheels.yml"
        )
        assert release.get("needs") == ["build-wheels"], (
            "expected Rust variant release job to wait for platform wheels"
        )
        assert "pure-wheel" not in jobs, (
            "expected Rust variant release workflow to skip pure wheel job"
        )
    else:
        assert "pure-wheel" in jobs, (
            "expected pure-Python release workflow to build one pure wheel"
        )
        assert release.get("needs") == ["pure-wheel"], (
            "expected pure-Python release job to wait for the pure wheel"
        )
        assert "build-wheels" not in jobs, (
            "expected pure-Python release workflow to skip platform wheel matrix"
        )


def assert_wheel_workflow_contracts(
    *,
    build_wheels_workflow: str,
    build_wheels_action: str,
    pure_wheel_action: str,
) -> None:
    """Assert generated wheel workflow and action contracts."""
    parsed_build_wheels = parse_yaml_mapping(
        build_wheels_workflow,
        "build-wheels workflow",
    )
    build_jobs = require_mapping(parsed_build_wheels, "jobs", "build-wheels workflow")
    build_job = require_mapping(build_jobs, "build", "build-wheels workflow jobs")
    strategy = require_mapping(build_job, "strategy", "build-wheels build job")
    matrix = require_mapping(strategy, "matrix", "build-wheels strategy")
    includes = require_sequence(matrix, "include", "build-wheels matrix")
    assert len(includes) == 6, (
        "expected build-wheels workflow to cover Linux, Windows, and macOS"
    )
    assert "persist-credentials: false" in build_wheels_workflow, (
        "expected build-wheels workflow checkout to disable credentials"
    )
    assert "uvx --with 'cibuildwheel>=2.16.0,<4.0.0' cibuildwheel" in (
        build_wheels_action
    ), "expected Rust wheel action to build through cibuildwheel"
    assert "persist-credentials: false" in build_wheels_action, (
        "expected build-wheels action checkout to disable credentials"
    )
    assert "uv build --wheel" in pure_wheel_action, (
        "expected pure-wheel action to build through uv"
    )
    assert "persist-credentials: false" in pure_wheel_action, (
        "expected pure-wheel action checkout to disable credentials"
    )


def checkout_steps_disable_credentials(steps: list[Any]) -> bool:
    """Return whether all checkout steps disable credential persistence."""
    checkout_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    return bool(checkout_steps) and all(
        isinstance(step.get("with"), dict)
        and step["with"].get("persist-credentials") is False
        for step in checkout_steps
    )
