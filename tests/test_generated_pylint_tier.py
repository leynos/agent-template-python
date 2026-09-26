"""Validate the rendered Pylint tier on its error path.

These integration tests render a project from the Copier template and run the
rendered Makefile's own ``$(PYLINT)`` command, rather than inspecting only the
generated text. They prove three properties of the generated tier: it picks an
interpreter that parses the project's baseline syntax, it passes a module using
the newest syntax that baseline allows, and it fails with ``syntax-error`` on a
module no interpreter can parse. The last property is the one a disabled
``syntax-error`` used to break silently: an unparsable module produced no
messages and the tier passed.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture, CopierProject

from tests.helpers.rendering import render_project

_PROBE_TARGET = "jm-pylint-probe"

# Each baseline's newest syntax the rendered tier must accept: PEP 695 type
# aliases on 3.12, and PEP 758 unparenthesized ``except`` lists on 3.14.
_BASELINE_SYNTAX = {
    "3.12": '"""Probe module."""\n\ntype Alias = list[int]\n',
    "3.14": (
        '"""Probe module."""\n\n\n'
        "def probe() -> int:\n"
        '    """Return one."""\n'
        "    try:\n"
        "        return 1\n"
        "    except ValueError, TypeError:\n"
        "        return 0\n"
    ),
}
_EXPECTED_INTERPRETER = {"3.12": "pypy@3.12", "3.14": "3.14"}


def _run_rendered_pylint(
    project: CopierProject, target: Path
) -> subprocess.CompletedProcess[str]:
    """Run the rendered Makefile's ``$(PYLINT)`` over one module.

    Parameters
    ----------
    project : CopierProject
        Rendered project whose Makefile defines ``PYLINT``.
    target : Path
        Module to lint.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished Make process with output captured.
    """
    make = shutil.which("make")
    assert make is not None, "expected make to be available for generated tests"
    quoted = shlex.quote(str(target)).replace("$", "$$")
    return subprocess.run(
        [
            make,
            "--no-print-directory",
            "-s",
            "--eval",
            f"{_PROBE_TARGET}: ; $(PYLINT) {quoted}",
            _PROBE_TARGET,
        ],
        cwd=project.path,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("python_version", ["3.12", "3.14"])
def test_rendered_pylint_tier_parses_the_baseline_and_fails_on_a_parse_error(
    copier: CopierFixture, tmp_path: Path, python_version: str
) -> None:
    """The rendered tier accepts the baseline's syntax and fails on a parse error.

    Parameters
    ----------
    copier : CopierFixture
        Fixture used to render the template into a temporary project.
    tmp_path : Path
        Temporary directory used as the generated project root.
    python_version : str
        Minimum supported Python version answer passed to Copier.
    """
    project = render_project(
        tmp_path / f"pylint-tier-{python_version}",
        copier,
        project_name="PylintTier",
        package_name="pylint_tier_pkg",
        use_rust=False,
        python_version=python_version,
    )
    makefile = (project / "Makefile").read_text(encoding="utf-8")
    declared = re.search(r"^PYLINT_PYTHON \?= (\S+)$", makefile, re.MULTILINE)
    assert declared is not None, "expected the rendered Makefile to set PYLINT_PYTHON"
    assert declared.group(1) == _EXPECTED_INTERPRETER[python_version], (
        f"expected PYLINT_PYTHON {_EXPECTED_INTERPRETER[python_version]} for a "
        f"{python_version} baseline, got {declared.group(1)}"
    )

    modern = tmp_path / "modern_module.py"
    modern.write_text(_BASELINE_SYNTAX[python_version], encoding="utf-8")
    passed = _run_rendered_pylint(project, modern)
    assert passed.returncode == 0, (
        f"expected the {python_version} baseline's syntax to lint clean:\n"
        f"{passed.stdout}\n{passed.stderr}"
    )

    broken = tmp_path / "broken_module.py"
    broken.write_text("def broken(\n    return 1\n", encoding="utf-8")
    failed = _run_rendered_pylint(project, broken)
    assert failed.returncode != 0, (
        f"expected an unparsable module to fail the tier:\n{failed.stdout}"
    )
    assert "syntax-error" in failed.stdout, (
        f"expected the failure to be the parse error:\n{failed.stdout}\n{failed.stderr}"
    )
