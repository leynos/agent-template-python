"""Render generated projects and run their public commands in tests."""

from __future__ import annotations

import shlex
from pathlib import Path

from pytest_copier.plugin import CopierFixture, CopierProject


def run_quality_gates(project: CopierProject) -> None:
    """Run the rendered project's public quality gate.

    Parameters
    ----------
    project : CopierProject
        Rendered ``pytest-copier`` project whose root contains the generated
        Makefile.

    Returns
    -------
    None
        The helper returns after the generated ``make all`` target succeeds.

    Raises
    ------
    AssertionError
        Raised by ``pytest-copier`` when the generated command exits
        unsuccessfully.
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
    tmp_path : pathlib.Path
        Temporary directory used as the generated project destination.
    copier : CopierFixture
        ``pytest-copier`` fixture bound to this template repository.
    project_name : str
        Project name answer passed to Copier.
    package_name : str
        Python import package name answer passed to Copier.
    use_rust : bool, default=False
        Whether to include the optional PyO3 extension.
    python_version : str, default="3.10"
        Minimum supported Python version answer passed to Copier.

    Returns
    -------
    CopierProject
        Rendered project wrapper for file assertions and command execution.

    Raises
    ------
    Exception
        Propagates rendering failures raised by Copier or ``pytest-copier``.
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
    project : CopierProject
        Rendered project whose managed environment should contain the package.
    package : str
        Import name to load through ``importlib.import_module``.
    greeting : str
        Expected return value from the generated package's ``hello`` function.

    Returns
    -------
    None
        The helper returns when the generated import and assertion succeed.

    Raises
    ------
    AssertionError
        Raised by ``pytest-copier`` when the generated command exits
        unsuccessfully.
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
    project : CopierProject
        Rendered ``pytest-copier`` project to read from.
    relative_path : str
        Path to the generated file, relative to the rendered project root.

    Returns
    -------
    str
        File contents decoded as UTF-8 text.

    Raises
    ------
    FileNotFoundError
        Raised when the requested generated file does not exist.
    OSError
        Raised when the file exists but cannot be read.
    """
    return (project / relative_path).read_text(encoding="utf-8")
