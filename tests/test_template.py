from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

from pytest_copier.plugin import CopierFixture, CopierProject


def build_package(project: CopierProject) -> None:
    """Install the generated package in editable mode."""
    project.run(f"{sys.executable} -m pip install -e .")
    import importlib
    import site
    import pathlib

    sp = site.getsitepackages()[0]
    for p in pathlib.Path(sp).glob("*.pth"):
        site.addsitedir(str(pathlib.Path(p.read_text().strip()).parent))
    importlib.invalidate_caches()


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

    assert not (proj / "rust_extension").exists()
    assert not (proj / "docs").exists()
    assert "maturin" not in (proj / "pyproject.toml").read_text()

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

    assert (proj / "rust_extension").exists()
    assert (proj / "docs" / "rust-extension.md").exists()
    assert "maturin" in (proj / "pyproject.toml").read_text()

    pkg = import_package("rust_pkg")
    assert pkg.hello() == "hello from Rust"


def test_rust_template_custom_package(copier: CopierFixture, tmp_path: Path) -> None:
    """Ensure templating uses the provided package name."""
    proj = copier.copy(
        tmp_path / "rust_custom",
        project_name="RustProj",
        package_name="custom_pkg",
        use_rust=True,
    )
    build_package(proj)
    check_static(proj)

    assert (proj / "rust_extension").exists()
    text = (proj / "pyproject.toml").read_text()
    assert "custom_pkg" in text

    pkg = import_package("custom_pkg")
    assert pkg.hello() == "hello from Rust"
