"""Validate rendered Makefile contracts and parsed command recipes.

This module owns Makefile-specific assertions for generated projects.  The
AGENTS contract helper imports ``_parse_makefile_rules`` from here so
documented commands can be compared against the parsed recipes without keeping
all contract domains in one large module.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import make_parser


def assert_common_make_targets(makefile: str) -> None:
    """Assert Makefile targets shared by all generated variants.

    Parameters
    ----------
    makefile : str
        UTF-8 text of a generated Makefile.

    Returns
    -------
    None
        The helper returns after all shared Makefile assertions pass.

    Raises
    ------
    AssertionError
        Raised when a shared generated Makefile target or cleanup path is
        missing.

    Examples
    --------
    Validate shared targets after reading a generated Makefile::

        assert_common_make_targets(makefile)
    """
    assert "lint-python: build" in makefile, "Makefile should expose lint-python"
    assert "lint: lint-python" in makefile, "lint should delegate to lint-python"
    assert "audit: build" in makefile, "Makefile should expose audit"
    assert ".uv-cache .uv-tools" in makefile, "clean should remove uv state dirs"


def _parse_makefile_rules(makefile: str) -> dict[str, list[str]]:
    """Return generated Makefile rules parsed through make-parser."""
    target_names = set(
        re.findall(r"^([a-zA-Z][a-zA-Z_-]*):", makefile, flags=re.MULTILINE)
    )
    normalised_targets = {
        target: target.replace("-", "_") for target in target_names if "-" in target
    }

    def normalise_target(match: re.Match[str]) -> str:
        """Replace hyphenated target names with parser-compatible aliases."""
        target = match.group(1)
        return normalised_targets.get(target, target) + ":"

    normalised_makefile = re.sub(
        r"^([a-zA-Z][a-zA-Z_-]*):",
        normalise_target,
        makefile.replace("?=", "="),
        flags=re.MULTILINE,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        makefile_path = Path(tmp_dir) / "Makefile"
        makefile_path.write_text(normalised_makefile, encoding="utf-8")
        parsed = make_parser.make_load(makefile_path)
    normalised_rules = parsed["rules"]
    return {
        target: normalised_rules[normalised_targets.get(target, target)]["commands"]
        for target in target_names
        if normalised_targets.get(target, target) in normalised_rules
    }


def _assert_makefile_contracts(*, makefile: str, use_rust: bool) -> None:
    """Assert generated Makefile contracts for both template variants."""
    assert_common_make_targets(makefile)
    assert "WITH_ACT ?= 0" in makefile, (
        "expected generated Makefile to default act validation off"
    )
    assert "ACT_TEST_ENV =" in makefile, (
        "expected generated Makefile to map WITH_ACT to pytest environment"
    )
    assert "RUN_ACT_VALIDATION=1" in makefile, (
        "expected generated Makefile to enable act validation for pytest"
    )
    assert "$(UV_ENV) $(ACT_TEST_ENV) $(UV) run pytest" in makefile, (
        "expected generated test target to include the act test environment"
    )
    assert "PYTHON_TARGETS ?=" in makefile, (
        "expected generated Makefile to define Python target selection"
    )
    assert "PYLINT_PYPY_SHIM_REF ?=" in makefile, (
        "expected generated Makefile to expose the Pylint shim revision"
    )
    assert "test: build $(VENV_TOOLS)" in makefile, (
        "expected generated Makefile test target to depend on the project env"
    )
    assert "$(UV_ENV) $(UV) run pip-audit" in makefile, (
        "expected generated audit target to run pip-audit"
    )
    assert "$(UV_ENV) $(UV) run interrogate --fail-under 100" in makefile, (
        "expected generated lint target to enforce docstring coverage"
    )
    if use_rust:
        assert "TEST_CMD :=" in makefile, (
            "expected Rust variant to select nextest or cargo test"
        )
        assert "lint-rust: build whitaker" in makefile, (
            "expected Rust variant to expose the Rust lint target"
        )
        assert "cargo is required for Rust tests" in makefile, (
            "expected Rust variant to fail clearly without cargo"
        )
        assert "$(CARGO) $(TEST_CMD) $(TEST_FLAGS)" in makefile, (
            "expected Rust variant tests to use the selected cargo test command"
        )
        assert "ifneq ($(TEST_CMD),test)" not in makefile, (
            "expected Rust variant tests to run doctests even when nextest is absent"
        )
        assert (
            'RUSTFLAGS="$(RUST_FLAGS)" $(CARGO) test --doc '
            "--manifest-path $(RUST_CRATE_DIR)/Cargo.toml --all-features"
        ) in makefile, "expected Rust variant tests to run Rust doctests"
        assert "rust-audit:" in makefile, (
            "expected Rust variant to expose the rust-audit target"
        )
        assert "cd $(RUST_CRATE_DIR) && $(CARGO) audit" in makefile, (
            "expected Rust variant audit target to run cargo audit"
        )
    else:
        assert "lint-rust" not in makefile, (
            "expected pure-Python variant to omit Rust lint targets"
        )
        assert "TEST_CMD :=" not in makefile, (
            "expected pure-Python variant to omit Rust test command selection"
        )
        assert "rust-audit" not in makefile, (
            "expected pure-Python variant to omit Rust audit targets"
        )
