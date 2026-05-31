"""Render generated projects and run their public commands in tests."""

from __future__ import annotations

import shlex
from pathlib import Path

from pytest_copier.plugin import CopierFixture, CopierProject


def run_quality_gates(project: CopierProject) -> None:
    """Run the rendered project's public quality gate."""
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
    """Render a generated Python project with explicit template answers."""
    return copier.copy(
        tmp_path,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
        python_version=python_version,
    )


def check_generated_import(project: CopierProject, package: str, greeting: str) -> None:
    """Import a generated package and assert its greeting."""
    script = (
        "import importlib; "
        f"module = importlib.import_module({package!r}); "
        f"assert module.hello() == {greeting!r}"
    )
    project.run(f"uv run python -c {shlex.quote(script)}")


def read_generated_file(project: CopierProject, relative_path: str) -> str:
    """Read a rendered project file as UTF-8 text."""
    return (project / relative_path).read_text(encoding="utf-8")
