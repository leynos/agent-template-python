"""Prove generated lint recipes reject representative policy violations.

Each case runs the rendered Makefile and its real pinned scanner. Only unrelated
checks and project installation are bypassed, keeping these boundary regressions
independent of full project builds. Existing generated-project tests exercise the
clean aggregate gate. Run these negative cases with
``pytest tests/test_lint_gate_failures.py``.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.rendering import initialize_git_repository, render_project

_CLONE_SOURCE = (
    "def normalize(value):\n"
    + "".join(
        f"    value = value.replace('item{index}', 'entry{index}')\n"
        for index in range(30)
    )
    + "    return value\n"
)


def _write_uv_launcher(path: Path) -> None:
    """Delegate to real uv while bypassing the unrelated Interrogate check."""
    uv = shutil.which("uv")
    assert uv is not None, "Generated scanner regressions require uv"
    path.write_text(
        "#!/bin/sh\n"
        'if [ "${1-}" = run ] && [ "${2-}" = interrogate ]; then\n'
        "    exit 0\n"
        "fi\n"
        f'exec {shlex.quote(uv)} "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.mark.parametrize(
    ("target", "overrides", "files", "diagnostics"),
    [
        pytest.param(
            "lint-python",
            ["RUFF=true", "PYLINT=true", "AMBRLEAKS=true"],
            {"tests/test_defect.py": "def test_policy():\n    assert True\n"},
            ["C9102", "test_defect.py"],
            id="df12-pylint-bare-assert",
        ),
        pytest.param(
            "lint-python",
            ["RUFF=true", "PYLINT=true", "DF12_PYLINT=true"],
            {
                "tests/__snapshots__/leak.ambr": (
                    "# serializer version: 1\n"
                    "# name: test_record\n"
                    "  '123e4567-e89b-12d3-a456-426614174000'\n"
                    "# ---\n"
                )
            },
            ["snapshot-uuid", "leak.ambr"],
            id="ambrleaks-unredacted-snapshot",
        ),
        pytest.param(
            "dead-code",
            ["SKYLOS=true"],
            {"tests/helpers.py": "def abandoned_helper():\n    return 42\n"},
            ["unused function", "abandoned_helper"],
            id="vulture-unused-test-helper",
        ),
        pytest.param(
            "duplication",
            [],
            {
                "scripts/clone_a.py": _CLONE_SOURCE,
                "scripts/clone_b.py": _CLONE_SOURCE,
            },
            ["duplicate code:", "clone_a.py", "clone_b.py"],
            id="nose-unsuppressed-clone",
        ),
    ],
)
def test_generated_lint_recipe_propagates_scanner_failure(
    copier: CopierFixture,
    tmp_path: Path,
    target: str,
    overrides: list[str],
    files: dict[str, str],
    diagnostics: list[str],
) -> None:
    """A planted defect reaches its configured scanner and makes Make fail."""
    project = render_project(
        tmp_path / "lint-failure",
        copier,
        project_name="LintFailure",
        package_name="lint_failure",
    )
    initialize_git_repository(project)
    for relative, content in files.items():
        source = project.path / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(content, encoding="utf-8")

    make = shutil.which("make")
    assert make is not None, "Generated scanner regressions require make"
    launcher = tmp_path / "uv-launcher"
    _write_uv_launcher(launcher)
    result = subprocess.run(
        [
            make,
            "--no-print-directory",
            "-o",
            "build",
            target,
            f"UV={launcher}",
            *overrides,
        ],
        cwd=project.path,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"Generated {target} accepted a planted scanner violation:\n{output}"
    )
    for diagnostic in diagnostics:
        assert diagnostic in output, (
            f"Expected {diagnostic!r} from the configured {target} scanner:\n{output}"
        )
