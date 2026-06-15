"""Validate rendered docstring coverage lint behaviour.

These integration tests render a project from the Copier template and exercise
its public ``make lint`` target instead of inspecting only generated text.  They
prove that a clean render passes the full Python lint tier, then mutate the
rendered package to introduce a Ruff-clean missing private docstring and verify
that Interrogate fails the target.

The module protects the template contract that generated projects enforce 100%
docstring coverage through their normal lint workflow.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pytest_copier.plugin import CopierFixture

from tests.helpers.rendering import render_project


def test_generated_make_lint_enforces_interrogate_docstrings(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Validate rendered ``make lint`` fails on missing private docstrings.

    Parameters
    ----------
    copier : CopierFixture
        Fixture used to render the template into a temporary project.
    tmp_path : Path
        Temporary directory used as the generated project root.

    Returns
    -------
    None
        The test passes when a complete generated project passes ``make lint``
        and a private helper without a docstring fails at the Interrogate gate.
    """
    package_name = "lint_docstrings_pkg"
    project = render_project(
        tmp_path / "lint-docstrings",
        copier,
        project_name="LintDocstrings",
        package_name=package_name,
        use_rust=False,
    )
    make = shutil.which("make")
    assert make is not None, "expected make to be available for generated tests"

    passing_result = subprocess.run(
        [make, "lint"],
        cwd=project.path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert passing_result.returncode == 0, (
        f"expected generated make lint to pass with complete docstrings:\n"
        f"{passing_result.stdout}\n{passing_result.stderr}"
    )

    pure_module = project / package_name / "pure.py"
    undocumented_helper = (
        '\n\ndef _missing_interrogate_docstring() -> str:\n    return "undocumented"\n'
    )
    pure_module.write_text(
        pure_module.read_text(encoding="utf-8") + undocumented_helper,
        encoding="utf-8",
    )

    failing_result = subprocess.run(
        [make, "lint"],
        cwd=project.path,
        check=False,
        capture_output=True,
        text=True,
    )
    output = f"{failing_result.stdout}\n{failing_result.stderr}"
    assert failing_result.returncode != 0, (
        "expected generated make lint to fail when Interrogate finds a missing "
        f"private docstring:\n{output}"
    )
    assert "RESULT: FAILED" in output, (
        "expected generated make lint to run the Interrogate docstring gate"
    )
    actual_match = re.search(r"actual:\s+([0-9]+(?:\.[0-9]+)?)%", output)
    assert actual_match is not None, (
        f"expected Interrogate output to report actual docstring coverage:\n{output}"
    )
    actual_coverage = float(actual_match.group(1))
    assert actual_coverage < 100.0, (
        "expected Interrogate output to report reduced docstring coverage"
    )
