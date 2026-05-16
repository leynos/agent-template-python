"""Validate generated Python-only and Rust-extension project templates."""

from __future__ import annotations

from pathlib import Path

from pytest_copier.plugin import CopierFixture, CopierProject


def run_quality_gates(project: CopierProject) -> None:
    """Run the generated project's public quality gates."""
    project.run("make all")


def check_generated_import(project: CopierProject, package: str, greeting: str) -> None:
    """Check the generated package inside its managed environment."""
    project.run(
        f'uv run python -c "import {package}; assert {package}.hello() == {greeting!r}"'
    )


def read_generated_file(project: CopierProject, relative_path: str) -> str:
    """Read a generated file as UTF-8 text."""
    return (project / relative_path).read_text(encoding="utf-8")


def assert_common_make_targets(makefile: str) -> None:
    """Assert shared generated Makefile targets and clean-up paths."""
    assert "lint-python: build" in makefile, "Makefile should expose lint-python"
    assert "lint: lint-python" in makefile, "lint should delegate to lint-python"
    assert ".uv-cache .uv-tools" in makefile, "clean should remove uv state dirs"


def test_python_only_template(copier: CopierFixture, tmp_path: Path) -> None:
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
    assert "lint-rust" not in makefile, "Python-only Makefile should not expose lint-rust"

    check_generated_import(proj, "pure_pkg", "hello from Python")


def test_rust_template(copier: CopierFixture, tmp_path: Path) -> None:
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
    assert "lint-rust: build whitaker" in makefile, "Rust Makefile should expose lint-rust"
    assert (
        "cargo is required for Rust tests" in makefile
    ), "Rust Makefile should fail clearly when cargo is unavailable"

    check_generated_import(proj, "rust_pkg", "hello from Rust")


def test_rust_template_custom_package(copier: CopierFixture, tmp_path: Path) -> None:
    """Ensure templating uses the provided package name."""
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
