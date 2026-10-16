"""Exercise the generated baseline and repository-wide lint boundaries."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.rendering import initialize_git_repository, render_project


@pytest.mark.parametrize("python_version", ["3.0", "3.9", "3.10", "3.11"])
def test_python_baseline_rejects_versions_below_312(
    copier: CopierFixture, tmp_path: Path, python_version: str
) -> None:
    """Copier rejects unsupported versions before generating a project."""
    with pytest.raises(ValueError, match=r"Python version must be 3\.12 or newer"):
        render_project(
            tmp_path / "unsupported",
            copier,
            project_name="Unsupported",
            package_name="unsupported",
            python_version=python_version,
        )


@pytest.mark.parametrize("use_rust", [False, True])
def test_lint_source_discovery_includes_new_scripts_and_hidden_actions(
    copier: CopierFixture, tmp_path: Path, use_rust: bool
) -> None:
    """Every source area reaches the lint recipe, including untracked files."""
    project = render_project(
        tmp_path / "discovery",
        copier,
        project_name="Discovery",
        package_name="discovery",
        use_rust=use_rust,
    )
    initialize_git_repository(project)
    for relative in ("scripts/new_script.py", ".github/actions/new/helper.py"):
        path = project.path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('"""New source."""\n', encoding="utf-8")
    result = subprocess.run(
        ["make", "-s", "--eval", "probe: ; @echo $(PYTHON_TARGETS)", "probe"],
        cwd=project.path,
        text=True,
        capture_output=True,
        check=True,
    )
    discovered = set(result.stdout.split())
    assert {"scripts/new_script.py", ".github/actions/new/helper.py"} <= discovered, (
        "Python source discovery omitted a new script or hidden action helper"
    )
    assert "scripts/action_workflow.py" in discovered, (
        "Python source discovery omitted the generated action workflow helper"
    )

    recipes = subprocess.run(
        ["make", "-n", "lint-python"],
        cwd=project.path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    expected = {"scripts/new_script.py", ".github/actions/new/helper.py"}
    for tool in ("ruff", "interrogate", "pylint"):
        commands = [line for line in recipes if f" {tool} " in line]
        assert commands, f"Expected generated lint to invoke {tool}"
        for command in commands:
            assert expected <= set(shlex.split(command)), command

    for target, fragment in (
        ("check-fmt", "format --check"),
        ("typecheck", "ty check"),
    ):
        target_recipes = subprocess.run(
            ["make", "-n", target],
            cwd=project.path,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        commands = [line for line in target_recipes if fragment in line]
        assert commands, f"Expected generated {target} to invoke {fragment}"
        for command in commands:
            assert expected <= set(shlex.split(command)), command


def test_native_entrypoint_keeps_unused_rust_helpers_reportable(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Only the PyO3 runtime initializer is exempt from the dead-code gate."""
    project = render_project(
        tmp_path / "native-boundary",
        copier,
        project_name="NativeBoundary",
        package_name="native_boundary",
        use_rust=True,
    )
    initialize_git_repository(project)
    clean = subprocess.run(
        ["make", "dead-code"],
        cwd=project.path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert clean.returncode == 0, clean.stdout + clean.stderr
    rust = project.path / "rust_extension" / "src" / "lib.rs"
    rust.write_text(
        rust.read_text(encoding="utf-8") + "\nfn unused_sibling() -> u32 { 1 }\n",
        encoding="utf-8",
    )
    failed = subprocess.run(
        ["make", "dead-code"],
        cwd=project.path,
        text=True,
        capture_output=True,
        check=False,
    )
    output = failed.stdout + failed.stderr
    assert failed.returncode != 0, "An unused sibling must still block the gate"
    assert "unused_sibling" in output, output
    assert "SKY-U001" in output, output
    assert "unused function: _native_boundary_rs" not in output, output
