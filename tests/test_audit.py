"""Validate rendered dependency audit Makefile targets.

This module exercises the generated ``make audit`` target for pure-Python and
Python/Rust renders without contacting external vulnerability databases.  The
tests use fake ``uv`` and ``cargo`` executables to record the audit commands
that the rendered Makefile dispatches.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
)
from tests.helpers.rendering import render_project


@pytest.mark.parametrize(
    ("target_dir", "project_name", "package_name", "use_rust"),
    [
        ("audit-pure", "AuditPure", "audit_pure", False),
        ("audit-rust", "AuditRust", "audit_rust", True),
    ],
)
def test_generated_audit_target_runs_expected_tools(
    copier: CopierFixture,
    tmp_path: Path,
    target_dir: str,
    project_name: str,
    package_name: str,
    use_rust: bool,
) -> None:
    """Validate generated audit target command dispatch.

    Parameters
    ----------
    copier : CopierFixture
        Fixture used to render the template into a temporary project.
    tmp_path : Path
        Temporary directory used for the rendered project and fake tools.
    target_dir : str
        Temporary project directory name for the rendered variant.
    project_name : str
        Project name answer passed to Copier.
    package_name : str
        Package name answer passed to Copier.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.

    Returns
    -------
    None
        The test passes when ``make audit`` runs ``pip-audit`` for every
        variant and runs ``cargo audit`` only for Rust-enabled projects.
    """
    project = render_project(
        tmp_path / target_dir,
        copier,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
    )
    command_log = tmp_path / f"{target_dir}-audit.log"
    fake_uv = _write_fake_uv(tmp_path / f"{target_dir}-bin", command_log)
    fake_cargo = _write_fake_cargo(tmp_path / f"{target_dir}-cargo", command_log)
    make = shutil.which("make")
    assert make is not None, "expected make to be available for generated tests"

    result = subprocess.run(
        [make, "audit", f"UV={fake_uv}", f"CARGO={fake_cargo}"],
        cwd=project.path,
        check=False,
        capture_output=True,
        text=True,
    )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, output
    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert "uv|pip-audit" in log_lines, (
        "expected generated audit target to run pip-audit through uv"
    )
    if use_rust:
        assert f"cargo|{project.path / 'rust_extension'}|audit" in log_lines, (
            "expected Rust-enabled audit target to run cargo audit in rust_extension"
        )
    else:
        assert all(not line.startswith("cargo|") for line in log_lines), (
            "expected pure-Python audit target to omit cargo audit"
        )


@pytest.mark.parametrize(
    ("target_dir", "project_name", "package_name", "use_rust"),
    [
        ("audit-workflow-pure", "AuditWorkflowPure", "audit_workflow_pure", False),
        ("audit-workflow-rust", "AuditWorkflowRust", "audit_workflow_rust", True),
    ],
)
def test_generated_audit_workflow_has_expected_contract(
    copier: CopierFixture,
    tmp_path: Path,
    target_dir: str,
    project_name: str,
    package_name: str,
    *,
    use_rust: bool,
) -> None:
    """Validate generated scheduled audit workflow structure."""
    project = render_project(
        tmp_path / target_dir,
        copier,
        project_name=project_name,
        package_name=package_name,
        use_rust=use_rust,
    )
    workflow_text = (project.path / ".github/workflows/audit.yml").read_text(
        encoding="utf-8"
    )
    workflow = parse_yaml_mapping(workflow_text, "audit workflow")
    workflow_triggers = workflow.get(True)
    assert isinstance(workflow_triggers, dict), (
        "expected generated audit workflow to include triggers"
    )
    assert "workflow_dispatch" in workflow_triggers, (
        "expected generated audit workflow to support manual dispatch"
    )
    schedule = require_sequence(workflow_triggers, "schedule", "audit workflow trigger")
    assert schedule == [{"cron": "11 7 * * 1"}], (
        "expected generated audit workflow to run weekly"
    )
    permissions = require_mapping(workflow, "permissions", "audit workflow")
    assert permissions == {"contents": "read"}, (
        "expected generated audit workflow to use read-only contents permission"
    )
    jobs = require_mapping(workflow, "jobs", "audit workflow")
    audit_job = require_mapping(jobs, "audit", "audit workflow jobs")
    assert audit_job.get("timeout-minutes") == 30, (
        "expected generated audit workflow to cap audit job runtime"
    )
    steps = require_sequence(audit_job, "steps", "audit workflow audit job")
    audit_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Audit dependencies"
    ]
    assert len(audit_steps) == 1, (
        "expected generated audit workflow to include one dependency audit step"
    )
    assert audit_steps[0].get("run") == "make audit", (
        "expected generated audit workflow to run the dependency audit target"
    )
    step_names = [step.get("name") for step in steps if isinstance(step, dict)]
    rust_step_names = {"Set up Rust", "Install cargo-audit"}
    if use_rust:
        assert rust_step_names.issubset(step_names), (
            "expected Rust audit workflow to include Rust audit setup"
        )
        install_steps = [
            step
            for step in steps
            if isinstance(step, dict) and step.get("name") == "Install cargo-audit"
        ]
        assert len(install_steps) == 1, (
            "expected Rust audit workflow to include one cargo-audit install step"
        )
        assert install_steps[0].get("run") == "cargo install --locked cargo-audit", (
            "expected Rust audit workflow to install cargo-audit with a locked build"
        )
    else:
        assert rust_step_names.isdisjoint(step_names), (
            "expected pure-Python audit workflow to omit Rust audit setup"
        )


def _write_fake_uv(bin_dir: Path, command_log: Path) -> Path:
    """Write a fake uv executable that records audit invocations."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    uv_path = bin_dir / "uv"
    uv_path.write_text(
        "#!/usr/bin/env sh\n"
        'if [ "$1" = venv ]; then\n'
        "  mkdir -p .venv/bin\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = sync ]; then\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = run ]; then\n'
        "  shift\n"
        f"  printf 'uv|%s\\n' \"$*\" >> '{command_log}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    uv_path.chmod(0o755)
    return uv_path


def _write_fake_cargo(bin_dir: Path, command_log: Path) -> Path:
    """Write a fake cargo executable that records audit invocations."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    cargo_path = bin_dir / "cargo"
    cargo_path.write_text(
        "#!/usr/bin/env sh\n"
        'if [ "$1" = audit ]; then\n'
        f"  printf 'cargo|%s|%s\\n' \"$PWD\" \"$*\" >> '{command_log}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    cargo_path.chmod(0o755)
    return cargo_path
