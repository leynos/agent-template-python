"""Validate conditional state-machine guidance in rendered AGENTS.md files."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

_STATE_MACHINE_GUIDANCE = (
    "Model mutually exclusive states explicitly",
    "correlated booleans, `Option` fields, sentinel values",
    "disguising an enum with state-specific payloads",
    "Choose state representation by who selects the transition",
    "prefer a runtime ADT",
    "explicit stack or other runtime structure for unbounded state",
    "Encapsulate transitions and mandatory finalization in the state owner",
    "semantic transition/result enums",
    "Keep genuinely independent booleans as booleans",
    "not merely to avoid `bool`",
)


@pytest.mark.parametrize("use_rust", [False, True])
def test_state_machine_guidance_is_limited_to_rust_extensions(
    copier: CopierFixture,
    tmp_path: Path,
    *,
    use_rust: bool,
) -> None:
    """Require state-machine guidance exactly when the Rust extension is enabled."""
    variant = "rust" if use_rust else "python"
    project = copier.copy(
        tmp_path / variant,
        project_name=f"StateMachine{variant.title()}",
        package_name=f"state_machine_{variant}",
        use_rust=use_rust,
    )
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")

    for fragment in _STATE_MACHINE_GUIDANCE:
        assert (fragment in agents) is use_rust, (
            "expected state-machine guidance presence to match the Rust-extension "
            f"setting for {fragment!r}"
        )
