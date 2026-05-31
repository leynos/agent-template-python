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
from pathlib import Path

import pytest
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

    assert not (
        proj / "rust_extension"
    ).exists(), "rust_extension directory should not exist for Python-only template"
    assert not (
        proj / "docs" / "rust-extension.md"
    ).exists(), "Rust documentation should not be generated for Python-only template"
    assert (
        "maturin" not in (proj / "pyproject.toml").read_text(encoding="utf-8")
    ), "maturin should not be in pyproject.toml for Python-only template"
    makefile = read_generated_file(proj, "Makefile")
    assert_common_make_targets(makefile)
    assert (
        "lint-rust" not in makefile
    ), "Python-only Makefile should not expose lint-rust"

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

    assert (
        proj / "rust_extension"
    ).exists(), "rust_extension directory should exist for Rust template"
    assert (
        proj / "docs" / "rust-extension.md"
    ).exists(), "Rust documentation should be generated for Rust template"
    assert (
        "maturin" in (proj / "pyproject.toml").read_text(encoding="utf-8")
    ), "maturin should be in pyproject.toml for Rust template"
    makefile = read_generated_file(proj, "Makefile")
    assert_common_make_targets(makefile)
    assert (
        "lint-rust: build whitaker" in makefile
    ), "Rust Makefile should expose lint-rust"
    assert (
        "cargo is required for Rust tests" in makefile
    ), "Rust Makefile should fail clearly when cargo is unavailable"

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

    assert (
        proj / "rust_extension"
    ).exists(), "rust_extension directory should exist for custom package Rust template"
    text = (proj / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        "custom_pkg" in text
    ), "custom package name should appear in pyproject.toml"

    check_generated_import(proj, "custom_pkg", "hello from Rust")
