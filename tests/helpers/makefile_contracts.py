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
    assert re.search(r"^lint-python:[^\n]*\bbuild\b", makefile, re.MULTILINE), (
        "Makefile should expose lint-python with its build prerequisite"
    )
    assert "lint: lint-python" in makefile, "lint should delegate to lint-python"
    assert "audit: build" in makefile, "Makefile should expose audit"
    assert "spelling:" in makefile, "Makefile should expose spelling"
    assert "TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.3" in makefile, (
        "Makefile should pin the shared typos-config-builder"
    )
    assert "git+https://github.com/leynos/typos-config-builder.git@" in makefile, (
        "spelling should install the builder from its pinned repository"
    )
    assert "gate --repository ." in makefile, (
        "spelling should run the shared gate over the generated repository"
    )
    assert ".uv-cache .uv-tools" in makefile, "clean should remove uv state dirs"


def _parse_makefile_rules(makefile: str) -> dict[str, list[str]]:
    """Return generated Makefile rules parsed through make-parser."""
    target_names = set(
        re.findall(r"^([a-zA-Z][a-zA-Z_-]*):", makefile, flags=re.MULTILINE)
    )
    normalized_targets = {
        target: target.replace("-", "_") for target in target_names if "-" in target
    }

    def normalize_target(match: re.Match[str]) -> str:
        """Replace hyphenated target names with parser-compatible aliases."""
        target = match.group(1)
        return normalized_targets.get(target, target) + ":"

    normalized_makefile = re.sub(
        r"^([a-zA-Z][a-zA-Z_-]*):",
        normalize_target,
        makefile.replace("?=", "="),
        flags=re.MULTILINE,
    )
    with tempfile.TemporaryDirectory() as tmp_dir:
        makefile_path = Path(tmp_dir) / "Makefile"
        makefile_path.write_text(normalized_makefile, encoding="utf-8")
        parsed = make_parser.make_load(makefile_path)
    normalized_rules = parsed["rules"]
    return {
        target: normalized_rules[normalized_targets.get(target, target)]["commands"]
        for target in target_names
        if normalized_targets.get(target, target) in normalized_rules
    }


def _assert_makefile_contracts(*, makefile: str, use_rust: bool) -> None:
    """Assert generated Makefile contracts for both template variants."""
    assert_common_make_targets(makefile)
    _assert_python_source_discovery_contract(makefile)
    lint_rule = re.search(r"^lint:([^#\n]*)", makefile, flags=re.MULTILINE)
    assert lint_rule is not None, "Makefile should expose the aggregate lint target"
    lint_dependencies = set(lint_rule.group(1).split())
    required_gates = {"lint-python", "dead-code", "duplication", "lint-actions"}
    assert required_gates <= lint_dependencies, (
        f"aggregate lint omitted required gates: {required_gates - lint_dependencies}"
    )
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
    assert "PYLINT_PYTHON ?= pypy@3.12" in makefile, (
        "expected generated Makefile to pin PyPy to its minor version"
    )
    assert "PYLINT_VERSION ?= 4.0.9" in makefile, (
        "expected generated Makefile to default to the reviewed Pylint release"
    )
    assert "--from 'pylint==$(PYLINT_VERSION)' pylint" in makefile, (
        "expected generated Pylint command to run the pinned release"
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
    assert "+$(MAKE) spelling" in makefile, (
        "expected generated aggregate gate to serialize spelling last"
    )
    if use_rust:
        assert re.search(r"^lint:[^#\n]*\blint-rust\b", makefile, re.MULTILINE), (
            "Rust variant aggregate lint should include lint-rust"
        )
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


def _assert_python_source_discovery_contract(makefile: str) -> None:
    """Require Python gates to check Git discovery before build tools.

    Parameters
    ----------
    makefile : str
        UTF-8 text of a generated Makefile.

    Returns
    -------
    None
        The helper returns after checking the source-discovery prerequisites.

    Raises
    ------
    AssertionError
        Raised when a guarded target omits the checked prerequisite or when
        help/build become dependent on Git source discovery.
    """

    def prerequisites(target: str) -> list[str]:
        """Return one target's prerequisites before its optional help text."""
        rule = re.search(
            rf"^{re.escape(target)}:([^\n]*)", makefile, flags=re.MULTILINE
        )
        assert rule is not None, f"Makefile should expose the {target} target"
        return rule.group(1).split("##", maxsplit=1)[0].split()

    logical_makefile = makefile.replace("\\\n", " ")
    phony_declarations = re.findall(r"(?m)^\.PHONY:[^\n]*", logical_makefile)
    assert any(
        re.search(r"\bcheck-python-sources\b", declaration)
        for declaration in phony_declarations
    ), "Python source discovery should be a phony Make target"

    for target in ("all", "fmt", "check-fmt", "lint-python", "typecheck"):
        target_prerequisites = prerequisites(target)
        assert target_prerequisites[0] == "check-python-sources", (
            f"{target} should check Git source discovery before other prerequisites"
        )
        assert "build" in target_prerequisites[1:], (
            f"{target} should preserve its build prerequisite after source discovery"
        )

    for target in ("help", "build"):
        assert "check-python-sources" not in prerequisites(target), (
            f"{target} should remain independent of Git source discovery"
        )
