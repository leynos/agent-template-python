"""Validate generated Go and Rust toolchain workflow contracts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.ci_contracts import (
    assert_go_toolchain_contract,
    assert_rust_cache_workspace_contract,
)
from tests.helpers.generated_files import (
    parse_yaml_mapping,
    read_generated_text,
    require_mapping,
    require_sequence,
)
from tests.helpers.rendering import render_project

_SETUP_RUST_USES_RE = re.compile(
    r"leynos/shared-actions/\.github/actions/setup-rust@[0-9a-f]{40}"
)
_INSTALL_MDTABLEFIX_USES = "leynos/shared-actions/.github/actions/install-mdtablefix@"


def _assert_setup_rust_precedes_mdtablefix(workflow_text: str, label: str) -> None:
    """Require pinned Rust setup before the Cargo-bootstrapped formatter."""
    workflow = parse_yaml_mapping(workflow_text, label)
    jobs = require_mapping(workflow, "jobs", label)
    lint_test = require_mapping(jobs, "lint-test", f"{label} jobs")
    steps = require_sequence(lint_test, "steps", f"{label} lint-test job")
    setup_indices: list[int] = []
    formatter_indices: list[int] = []

    for index, step_value in enumerate(steps):
        assert isinstance(step_value, dict), (
            f"expected {label} step {index} to be a mapping"
        )
        uses = step_value.get("uses")
        if isinstance(uses, str) and uses.startswith(
            "leynos/shared-actions/.github/actions/setup-rust@"
        ):
            assert _SETUP_RUST_USES_RE.fullmatch(uses), (
                f"expected {label} Rust setup to use a full 40-character SHA, "
                f"got {uses!r}"
            )
            setup_indices.append(index)
        if isinstance(uses, str) and uses.startswith(_INSTALL_MDTABLEFIX_USES):
            formatter_indices.append(index)

    assert len(setup_indices) == 1, f"expected one pinned Rust setup in {label}"
    assert len(formatter_indices) == 1, (
        f"expected one shared mdtablefix installer in {label}"
    )
    assert setup_indices[0] < formatter_indices[0], (
        f"expected {label} to set up Rust before installing mdtablefix"
    )


@pytest.mark.parametrize(("use_rust", "variant"), [(False, "pure"), (True, "rust")])
def test_rendered_actionlint_workflows_set_up_go_first(
    copier: CopierFixture, tmp_path: Path, use_rust: bool, variant: str
) -> None:
    """Pure and Rust CI renders provision Go before installing Actionlint."""
    project = render_project(
        tmp_path / variant,
        copier,
        project_name=f"Actionlint{variant.title()}",
        package_name=f"actionlint_{variant}",
        use_rust=use_rust,
    )
    workflow_text = read_generated_text(project.path / ".github/workflows/ci.yml")
    assert_go_toolchain_contract(workflow_text, f"rendered {variant} CI workflow")


@pytest.mark.parametrize(("use_rust", "variant"), [(False, "pure"), (True, "rust")])
def test_rendered_workflows_set_up_rust_before_mdtablefix(
    copier: CopierFixture, tmp_path: Path, use_rust: bool, variant: str
) -> None:
    """Pure and Rust renders provision Cargo for shared Markdown tooling."""
    project = render_project(
        tmp_path / f"rust-toolchain-{variant}",
        copier,
        project_name=f"RustToolchain{variant.title()}",
        package_name=f"rust_toolchain_{variant}",
        use_rust=use_rust,
    )
    workflow_text = read_generated_text(project.path / ".github/workflows/ci.yml")
    assert_rust_cache_workspace_contract(
        workflow_text, use_rust=use_rust, label=f"rendered {variant} CI workflow"
    )
    _assert_setup_rust_precedes_mdtablefix(
        workflow_text, f"rendered {variant} CI workflow"
    )
