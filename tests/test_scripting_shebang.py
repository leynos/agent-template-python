"""Validate the PEP 723 uv script shebang standard.

``#!/usr/bin/env -S uv run python`` executes the interpreter directly and
silently ignores the PEP 723 inline metadata block (``# /// script`` ...
``# ///``), so a script invoked directly (``./script.py``) fails at import
time because its declared dependencies were never installed. The correct
shebang is ``#!/usr/bin/env -S uv run --script``, which reads the metadata
block and installs the declared dependencies before execution.

This module guards against the broken shebang reappearing anywhere in the
repository or the Copier template tree, and behaviourally proves that the
prescribed shebang works as intended.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BROKEN_SHEBANG = "#!/usr/bin/env -S uv run python"
CORRECT_SHEBANG = "#!/usr/bin/env -S uv run --script"
SCRIPT_BLOCK_MARKER = "# /// script"
EXCLUDED_DIRECTORY_NAMES = {".git"}
LOOKAHEAD_LINES = 5


def _iter_repository_files() -> list[Path]:
    """Return every tracked-style file under the repository, excluding VCS internals."""
    files: list[Path] = []
    for path in REPOSITORY_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if EXCLUDED_DIRECTORY_NAMES & set(path.relative_to(REPOSITORY_ROOT).parts):
            continue
        files.append(path)
    return files


def _find_broken_shebang_pep723_scripts() -> list[str]:
    """Return relative paths of files whose broken shebang heads a PEP 723 block.

    A violation is a line exactly matching ``BROKEN_SHEBANG`` with a
    ``# /// script`` marker within the next few lines, which indicates the
    shebang introduces a PEP 723 inline-metadata script rather than merely
    appearing in prose or an unrelated command example.
    """
    violations: list[str] = []
    for path in _iter_repository_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() != BROKEN_SHEBANG:
                continue
            lookahead = lines[index + 1 : index + 1 + LOOKAHEAD_LINES]
            if any(SCRIPT_BLOCK_MARKER in candidate for candidate in lookahead):
                violations.append(str(path.relative_to(REPOSITORY_ROOT)))
    return violations


def test_no_broken_uv_shebang_heads_a_pep723_script() -> None:
    """No file in the repository or template tree ships the broken shebang.

    Returns
    -------
    None
        The test passes when every PEP 723 script block is introduced by
        ``#!/usr/bin/env -S uv run --script`` rather than the broken
        ``#!/usr/bin/env -S uv run python`` form, which silently ignores the
        metadata block on direct execution.
    """
    violations = _find_broken_shebang_pep723_scripts()
    assert violations == [], (
        "expected no PEP 723 script to be headed by the broken "
        f"'{BROKEN_SHEBANG}' shebang; offending files: {violations}"
    )


def test_correct_uv_shebang_installs_declared_dependency(tmp_path: Path) -> None:
    """A script with the prescribed shebang installs and imports its dependency.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory used to host the executable script under test.

    Returns
    -------
    None
        The test passes when a directly executed script using
        ``#!/usr/bin/env -S uv run --script`` installs its declared
        dependency, imports it successfully, and exits with code ``0``.
    """
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        pytest.skip("uv is unavailable to exercise the shebang behaviourally")

    script_path = tmp_path / "shebang_probe.py"
    script_source = (
        f"{CORRECT_SHEBANG}\n"
        "# /// script\n"
        '# requires-python = ">=3.13"\n'
        '# dependencies = ["packaging"]\n'
        "# ///\n"
        "\n"
        "import packaging\n"
        "\n"
        'print(f"packaging-ok:{packaging.__version__}")\n'
    )
    script_path.write_text(script_source, encoding="utf-8")
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

    result = subprocess.run(  # noqa: S603 - argv is the freshly written temp script.
        [str(script_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, (
        "expected the correctly shebanged script to run and exit cleanly:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "packaging-ok:" in result.stdout, (
        "expected the script to successfully import its declared dependency:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
