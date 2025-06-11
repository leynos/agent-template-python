from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

from pytest_copier.plugin import CopierFixture, CopierProject


def build_package(project: CopierProject) -> None:
    """Install the generated package in editable mode."""
    project.run(f"{sys.executable} -m pip install -e .")


def check_static(project: CopierProject) -> None:
    """Run lint and type checks on the project."""
    project.run("ruff format --check .")
    project.run("ruff check .")
    project.run("pyright")


def import_package(package: str) -> ModuleType:
    """Import the generated package."""
    return importlib.import_module(package)


def test_python_only_template(copier: CopierFixture, tmp_path: Path) -> None:
    proj = copier.copy(
        tmp_path / "pure", project_name="Pure", package_name="pure_pkg", use_rust=False
    )
    build_package(proj)
    check_static(proj)

    pkg = import_package("pure_pkg")
    assert pkg.hello() == "hello from Python"


def test_rust_template(copier: CopierFixture, tmp_path: Path) -> None:
    proj = copier.copy(
        tmp_path / "rust",
        project_name="RustProj",
        package_name="rust_pkg",
        use_rust=True,
    )
    build_package(proj)
    check_static(proj)

    pkg = import_package("rust_pkg")
    assert pkg.hello() == "hello from Rust"
