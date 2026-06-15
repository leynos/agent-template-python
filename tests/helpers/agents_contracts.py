"""Validate rendered AGENTS.md contracts against generated Makefiles.

This module contains assistant-guidance assertions for rendered projects.  It
uses ``tests.helpers.makefile_contracts`` to parse generated Makefiles so the
documented targets and command flags are checked against the actual recipes.
"""

from __future__ import annotations

import re

from tests.helpers.makefile_contracts import _parse_makefile_rules


def _assert_agents_contracts(agents: str) -> None:
    """Assert generated assistant guidance documents act-enabled testing."""
    assert "make test WITH_ACT=1" in agents, (
        "expected generated AGENTS.md to document act-enabled test runs"
    )
    assert "RUN_ACT_VALIDATION=1" in agents, (
        "expected generated AGENTS.md to describe the pytest act environment"
    )
    assert "meaningful, reviewer-useful contracts" in agents, (
        "expected generated AGENTS.md to require meaningful snapshot contracts"
    )
    assert "generic dumps" in agents, (
        "expected generated AGENTS.md to warn against generic snapshots"
    )
    assert "semantic assertions" in agents, (
        "expected generated AGENTS.md to pair snapshots with semantic assertions"
    )
    assert "normalize nondeterministic fields" in agents, (
        "expected generated AGENTS.md to require nondeterministic field redaction"
    )
    assert "brittle snapshots" in agents, (
        "expected generated AGENTS.md to warn against brittle snapshot churn"
    )
    assert "Temporary lint suppressions must include a link" in agents, (
        "expected generated AGENTS.md to require linked plans for temporary "
        "lint suppressions"
    )
    assert "Keep pytest tests in the top-level `tests/` tree" in agents, (
        "expected generated AGENTS.md to keep pytest discovery compatible with "
        "xdist-backed coverage"
    )


def _assert_agents_make_targets_mirror_makefile(
    *, agents: str, makefile: str, package_name: str, use_rust: bool
) -> None:
    """Assert AGENTS.md make target references match parsed Makefile commands."""
    documented_targets = _documented_make_targets(agents)
    makefile_rules = _parse_makefile_rules(makefile)
    makefile_targets = set(makefile_rules)
    missing_targets = sorted(documented_targets - makefile_targets)
    assert not missing_targets, (
        "expected every make target documented in generated AGENTS.md to exist "
        f"in the generated Makefile, missing: {missing_targets}"
    )
    required_documented_targets = {
        "audit",
        "check-fmt",
        "fmt",
        "lint",
        "markdownlint",
        "nixie",
        "test",
        "typecheck",
    }
    missing_documented_targets = sorted(
        required_documented_targets - documented_targets
    )
    assert not missing_documented_targets, (
        "expected generated AGENTS.md to document the generated Makefile quality "
        f"gate targets, missing: {missing_documented_targets}"
    )
    _assert_documented_command_flags(
        agents=agents,
        makefile_rules=makefile_rules,
        package_name=package_name,
        use_rust=use_rust,
    )


def _assert_documented_command_flags(
    *,
    agents: str,
    makefile_rules: dict[str, list[str]],
    package_name: str,
    use_rust: bool,
) -> None:
    """Assert documented make command flags are present in parsed recipes."""
    python_targets = f"{package_name} tests"
    command_contracts = {
        "check-fmt": [
            ("AGENTS.md", "ruff format --check $(PYTHON_TARGETS)"),
            ("Makefile", f"ruff format --check {python_targets}"),
        ],
        "lint-python": [
            ("AGENTS.md", "ruff check $(PYTHON_TARGETS)"),
            ("AGENTS.md", "interrogate --fail-under 100 $(PYTHON_TARGETS)"),
            ("Makefile", f"ruff check {python_targets}"),
            ("Makefile", f"interrogate --fail-under 100 {python_targets}"),
        ],
        "typecheck": [
            ("AGENTS.md", "ty check $(PYTHON_TARGETS)"),
            ("Makefile", f"ty check {python_targets}"),
        ],
        "audit": [
            ("AGENTS.md", "pip-audit"),
            ("Makefile", "pip-audit"),
        ],
        "test": [
            ("AGENTS.md", "pytest -v -n $(PYTEST_XDIST_WORKERS)"),
            ("Makefile", "pytest -v -n auto"),
        ],
    }
    if use_rust:
        command_contracts.update(
            {
                "check-fmt": [
                    *command_contracts["check-fmt"],
                    (
                        "AGENTS.md",
                        "cargo fmt --manifest-path rust_extension/Cargo.toml",
                    ),
                    ("AGENTS.md", "--all -- --check"),
                    ("Makefile", "fmt --manifest-path rust_extension/Cargo.toml"),
                    ("Makefile", "--all -- --check"),
                ],
                "lint-rust": [
                    ("AGENTS.md", "cargo doc --no-deps"),
                    (
                        "AGENTS.md",
                        "cargo clippy --manifest-path rust_extension/Cargo.toml",
                    ),
                    ("AGENTS.md", "--all-targets --all-features -- -D warnings"),
                    ("AGENTS.md", "whitaker --all -- --all-targets --all-features"),
                    ("Makefile", "doc --no-deps"),
                    ("Makefile", "clippy --manifest-path rust_extension/Cargo.toml"),
                    ("Makefile", "--all-targets --all-features -- -D warnings"),
                    ("Makefile", "--all -- --all-targets --all-features"),
                ],
                "test": [
                    *command_contracts["test"],
                    (
                        "AGENTS.md",
                        "cargo nextest run --manifest-path rust_extension/Cargo.toml",
                    ),
                    (
                        "AGENTS.md",
                        "cargo test --manifest-path rust_extension/Cargo.toml",
                    ),
                    (
                        "AGENTS.md",
                        "cargo test --doc --manifest-path rust_extension/Cargo.toml",
                    ),
                    ("Makefile", "--manifest-path rust_extension/Cargo.toml"),
                    ("Makefile", "--all-targets --all-features"),
                    (
                        "Makefile",
                        "test --doc --manifest-path rust_extension/Cargo.toml",
                    ),
                ],
                "audit": [
                    *command_contracts["audit"],
                    ("AGENTS.md", "cargo audit"),
                    ("Makefile", "$(MAKE) rust-audit"),
                ],
                "rust-audit": [
                    ("Makefile", "cd rust_extension"),
                    ("Makefile", ") audit"),
                ],
            }
        )
    for target, checks in command_contracts.items():
        assert target in makefile_rules, (
            "expected generated Makefile rules to include target "
            f"{target!r} from command_contracts"
        )
        commands = "\n".join(makefile_rules[target])
        for source, fragment in checks:
            haystack = agents if source == "AGENTS.md" else commands
            assert fragment in haystack, (
                f"expected generated {source} {target!r} command contract to "
                f"include {fragment!r}"
            )


def _documented_make_targets(agents: str) -> set[str]:
    """Return make targets referenced in rendered AGENTS.md guidance."""
    return set(re.findall(r"`make ([a-zA-Z][a-zA-Z_-]*)", agents))
