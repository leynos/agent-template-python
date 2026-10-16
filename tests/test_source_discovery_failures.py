"""Keep generated Python gates from running after Git discovery fails."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.makefile_contracts import _assert_python_source_discovery_contract
from tests.helpers.rendering import render_project

_PYTHON_GATES = ("all", "fmt", "check-fmt", "lint-python", "typecheck")
_DISCOVERY_ERROR = "Error: git ls-files failed while discovering Python sources"


def _source_discovery_makefile(phony_declaration: str) -> str:
    """Build a small Makefile fixture for source-discovery shape checks."""
    return f"""{phony_declaration}
check-python-sources:
all: check-python-sources build
fmt: check-python-sources build
check-fmt: check-python-sources build
lint-python: check-python-sources build
typecheck: check-python-sources build
help:
build:
"""


@pytest.mark.parametrize(
    "phony_declaration",
    [
        ".PHONY: all fmt check-fmt lint-python typecheck check-python-sources",
        ".PHONY: all fmt check-fmt lint-python typecheck \\\n        check-python-sources",
    ],
    ids=["first-line", "continued-line"],
)
def test_source_discovery_contract_accepts_phony_guard_positions(
    phony_declaration: str,
) -> None:
    """Accept the guard on either physical line of a continued PHONY rule."""
    _assert_python_source_discovery_contract(
        _source_discovery_makefile(phony_declaration)
    )


def test_source_discovery_contract_rejects_guard_removed_from_phony() -> None:
    """Require the source guard to remain phony when its prerequisites are valid."""
    makefile = _source_discovery_makefile(
        ".PHONY: all fmt check-fmt lint-python typecheck"
    )
    with pytest.raises(AssertionError, match="should be a phony Make target"):
        _assert_python_source_discovery_contract(makefile)


def test_source_discovery_contract_rejects_missing_guard_prerequisite() -> None:
    """Reject a target after its source-discovery prerequisite is removed."""
    makefile = _source_discovery_makefile(
        ".PHONY: all fmt check-fmt lint-python typecheck check-python-sources"
    ).replace("all: check-python-sources build", "all: build")
    with pytest.raises(AssertionError, match="all should check Git source discovery"):
        _assert_python_source_discovery_contract(makefile)


def test_source_discovery_contract_rejects_guard_after_build() -> None:
    """Reject a Python gate whose build can run before its source guard."""
    makefile = _source_discovery_makefile(
        ".PHONY: all fmt check-fmt lint-python typecheck check-python-sources"
    ).replace("\nfmt: check-python-sources build", "\nfmt: build check-python-sources")
    with pytest.raises(AssertionError, match="fmt should check Git source discovery"):
        _assert_python_source_discovery_contract(makefile)


def _write_probe(path: Path, contents: str) -> None:
    """Write an executable shell probe into a private PATH directory."""
    path.write_text("#!/bin/sh\n" + contents, encoding="utf-8")
    path.chmod(0o755)


def _probe_environment(
    bin_directory: Path, home: Path, *, git_log: Path | None
) -> dict[str, str]:
    """Return a minimal environment that cannot see the host Git binary."""
    environment = {
        "HOME": str(home),
        "PATH": str(bin_directory),
        "UV": str(bin_directory / "uv"),
        "MDTABLEFIX": str(bin_directory / "mdtablefix"),
        "UV_CALL_LOG": str(home / "uv-calls.log"),
        "TOOL_CALL_LOG": str(home / "tool-calls.log"),
    }
    if git_log is not None:
        environment["GIT_CALL_LOG"] = str(git_log)
    return environment


def _make_result(
    project: Path, environment: dict[str, str], target: str
) -> subprocess.CompletedProcess[str]:
    """Run one generated target without requiring a Git repository."""
    make = shutil.which("make")
    assert make is not None, "Generated source-discovery regressions require make"
    return subprocess.run(
        [make, "--no-print-directory", "-s", target],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_python_gates_fail_before_tools_when_git_listing_fails(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Preserve Git's error and stop every source gate before build/tool work."""
    project = render_project(
        tmp_path / "git-failure",
        copier,
        project_name="GitFailure",
        package_name="git_failure",
    )
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    git_log = home / "git-calls.log"
    _write_probe(
        bin_directory / "git",
        'printf "%s\\n" "$*" >> "$GIT_CALL_LOG"\n'
        "printf '%s\\n' 'fatal: controlled source discovery failure' >&2\n"
        "exit 23\n",
    )
    _write_probe(
        bin_directory / "uv",
        'printf "%s\\n" "$*" >> "$UV_CALL_LOG"\nexit 0\n',
    )
    _write_probe(
        bin_directory / "mdtablefix",
        'printf "%s\\n" "$*" >> "$TOOL_CALL_LOG"\nexit 0\n',
    )
    environment = _probe_environment(bin_directory, home, git_log=git_log)

    for target in _PYTHON_GATES:
        result = _make_result(project.path, environment, target)
        output = result.stdout + result.stderr
        assert result.returncode != 0, f"{target} passed after Git failed"
        assert _DISCOVERY_ERROR in output, output
        assert "fatal: controlled source discovery failure" in output, output
        assert not (home / "uv-calls.log").exists(), (
            f"{target} invoked build or Python tools after source discovery failed"
        )
        assert not (home / "tool-calls.log").exists(), (
            f"{target} invoked a formatting tool after source discovery failed"
        )

    git_calls = git_log.read_text(encoding="utf-8").splitlines()
    assert len(git_calls) == len(_PYTHON_GATES), git_calls
    assert all(
        call.startswith("ls-files --cached --others --exclude-standard")
        for call in git_calls
    ), (
        "the guard should use the same tracked-and-untracked Git listing as PYTHON_TARGETS"
    )


def test_python_gate_reports_missing_git_before_build(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Fail clearly when Git is absent from a generated project's PATH."""
    project = render_project(
        tmp_path / "no-git",
        copier,
        project_name="NoGit",
        package_name="no_git",
    )
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    _write_probe(
        bin_directory / "uv",
        'printf "%s\\n" "$*" >> "$UV_CALL_LOG"\nexit 0\n',
    )
    environment = _probe_environment(bin_directory, home, git_log=None)

    result = _make_result(project.path, environment, "lint-python")
    output = result.stdout + result.stderr

    assert result.returncode != 0, "lint-python should fail without Git discovery"
    assert _DISCOVERY_ERROR in output, output
    assert "git" in output.lower() and "not found" in output.lower(), output
    assert not (home / "uv-calls.log").exists(), (
        "lint-python should stop before invoking build or lint tools"
    )


def test_all_reports_real_git_failure_for_uninitialized_project(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Retain Git's fatal diagnostic when a rendered project lacks a repository."""
    project = render_project(
        tmp_path / "uninitialized-git",
        copier,
        project_name="UninitializedGit",
        package_name="uninitialized_git",
    )
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    git = shutil.which("git")
    assert git is not None, "Git source-discovery regressions require git"
    (bin_directory / "git").symlink_to(git)
    _write_probe(
        bin_directory / "uv",
        'printf "%s\\n" "$*" >> "$UV_CALL_LOG"\nexit 0\n',
    )
    environment = _probe_environment(bin_directory, home, git_log=None)

    result = _make_result(project.path, environment, "all")
    output = result.stdout + result.stderr

    assert result.returncode != 0, "all should fail outside a Git repository"
    assert "fatal: not a git repository" in output, output
    assert _DISCOVERY_ERROR in output, output
    assert not (home / "uv-calls.log").exists(), (
        "all should stop before its initial build when Git discovery fails"
    )


def test_explicit_python_targets_override_works_without_git(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Keep an explicit PYTHON_TARGETS override independent of Git discovery."""
    project = render_project(
        tmp_path / "source-override",
        copier,
        project_name="SourceOverride",
        package_name="source_override",
    )
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    uv_log = home / "uv-calls.log"
    _write_probe(
        bin_directory / "uv",
        'printf "%s\\n" "$*" >> "$UV_CALL_LOG"\nexit 0\n',
    )
    environment = _probe_environment(bin_directory, home, git_log=None)
    make = shutil.which("make")
    assert make is not None, "Generated source-discovery regressions require make"

    result = subprocess.run(
        [
            make,
            "--no-print-directory",
            "-s",
            "typecheck",
            "PYTHON_TARGETS=tests/override.py",
        ],
        cwd=project.path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    invocations = uv_log.read_text(encoding="utf-8").splitlines()
    assert any("check tests/override.py" in invocation for invocation in invocations), (
        "typecheck should pass the caller's explicit Python source list to ty"
    )
