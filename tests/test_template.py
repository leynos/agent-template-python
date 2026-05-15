from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from pytest_copier.plugin import CopierFixture, CopierProject


def run_quality_gates(project: CopierProject) -> None:
    """Run the generated project's public quality gates."""
    project.run("make check-fmt")
    project.run("make lint")
    project.run("make typecheck")
    project.run("make test")


def import_package(package: str) -> ModuleType:
    """Import the generated package."""
    return importlib.import_module(package)


def test_python_only_template(copier: CopierFixture, tmp_path: Path) -> None:
    proj = copier.copy(
        tmp_path / "pure", project_name="Pure", package_name="pure_pkg", use_rust=False
    )
    run_quality_gates(proj)

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
    run_quality_gates(proj)

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
    run_quality_gates(proj)

    assert (proj / "rust_extension").exists()
    text = (proj / "pyproject.toml").read_text()
    assert "custom_pkg" in text

    pkg = import_package("custom_pkg")
    assert pkg.hello() == "hello from Rust"
