"""Validate rendered pyproject packaging contracts.

This module contains pyproject-specific assertions extracted from
``tests.helpers.tooling_contracts``.  The top-level tooling-contract
orchestrator imports this private helper so packaging checks remain isolated
from Makefile and workflow assertions while sharing the generated-file parsing
helpers.
"""

from __future__ import annotations

from typing import Any

from tests.helpers.generated_files import require_mapping


def _assert_pyproject_contracts(
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
    for dependency in [
        "pytest",
        "interrogate",
        "pip-audit",
        "ruff",
        "pyright",
        "ty",
        "pytest-timeout",
        "pytest-xdist",
    ]:
        assert dependency in dev_dependencies, (
            f"expected generated dev dependencies to include {dependency}"
        )
    pytest_options = require_mapping(
        require_mapping(pyproject, "tool", "pyproject.toml"),
        "pytest",
        "pyproject.toml tool",
    )
    pytest_ini_options = require_mapping(
        pytest_options,
        "ini_options",
        "pyproject.toml tool.pytest",
    )
    assert pytest_ini_options.get("testpaths") == ["tests"], (
        "expected generated pytest discovery to be limited to the tests tree"
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
