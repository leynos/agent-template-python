"""Assert rendered tooling contracts for generated project variants.

This module contains the higher-level contract checks used after
``tests.helpers.rendering`` renders a project and
``tests.helpers.generated_files`` parses its structured files.  The public
helpers validate generated Makefile targets, packaging metadata, assistant
guidance, and GitHub workflow structure for both pure-Python and Python/Rust
variants.  Keep workflow and tooling assertions here so top-level template
tests stay focused on scenario setup.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import make_parser

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
)


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
    assert ".uv-cache .uv-tools" in makefile, "clean should remove uv state dirs"


def assert_generated_tooling_contracts(
    *,
    package_name: str,
    agents: str,
    pyproject: dict[str, Any],
    makefile: str,
    ci_workflow: str,
    release_workflow: str,
    build_wheels_workflow: str,
    build_wheels_action: str,
    pure_wheel_action: str,
    use_rust: bool,
) -> None:
    """Assert generated Python/Rust tooling contracts from one validator.

    Parameters
    ----------
    package_name : str
        Generated Python import package name.
    agents : str
        UTF-8 text of the generated ``AGENTS.md`` file.
    pyproject : dict[str, Any]
        Parsed generated ``pyproject.toml`` mapping.
    makefile : str
        UTF-8 text of the generated Makefile.
    ci_workflow : str
        UTF-8 text of the generated CI workflow.
    release_workflow : str
        UTF-8 text of the generated release workflow.
    build_wheels_workflow : str
        UTF-8 text of the generated build-wheels workflow.
    build_wheels_action : str
        UTF-8 text of the generated build-wheels composite action.
    pure_wheel_action : str
        UTF-8 text of the generated pure-wheel composite action.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.

    Returns
    -------
    None
        The helper returns after all generated tooling contracts pass.

    Raises
    ------
    AssertionError
        Raised when any generated tooling, workflow, or packaging contract is
        missing or variant-inconsistent.

    Examples
    --------
    Validate generated contracts after rendering a project::

        assert_generated_tooling_contracts(
            package_name="example_pkg",
            agents=agents,
            pyproject=pyproject,
            makefile=makefile,
            ci_workflow=ci_workflow,
            release_workflow=release_workflow,
            build_wheels_workflow=build_wheels_workflow,
            build_wheels_action=build_wheels_action,
            pure_wheel_action=pure_wheel_action,
            use_rust=False,
        )
    """
    parsed_ci_workflow = _parse_ci_workflow(ci_workflow)
    _assert_pyproject_contracts(
        package_name=package_name,
        pyproject=pyproject,
        use_rust=use_rust,
    )
    _assert_agents_contracts(agents)
    _assert_agents_make_targets_mirror_makefile(
        agents=agents,
        makefile=makefile,
        package_name=package_name,
        use_rust=use_rust,
    )
    _assert_makefile_contracts(makefile=makefile, use_rust=use_rust)
    _assert_ci_workflow_contracts(
        parsed_ci_workflow=parsed_ci_workflow,
        ci_workflow=ci_workflow,
        use_rust=use_rust,
    )
    _assert_release_workflow_contracts(
        release_workflow=release_workflow,
        use_rust=use_rust,
    )
    _assert_wheel_workflow_contracts(
        build_wheels_workflow=build_wheels_workflow,
        build_wheels_action=build_wheels_action,
        pure_wheel_action=pure_wheel_action,
    )


def assert_ci_coverage_action_contract(
    *, ci_workflow: str, package_name: str, use_rust: bool
) -> None:
    """Assert generated CI coverage inputs used by act validation.

    Parameters
    ----------
    ci_workflow : str
        UTF-8 text of the generated CI workflow.
    package_name : str
        Generated Python import package name used to derive the coverage
        artefact suffix.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.

    Returns
    -------
    None
        The helper returns after the coverage action contract matches
        expectations.

    Raises
    ------
    AssertionError
        Raised when checkout credentials, coverage action pinning, coverage
        output settings, artefact naming, or Rust manifest inputs are wrong.

    Examples
    --------
    Validate a rendered CI workflow's coverage step::

        assert_ci_coverage_action_contract(
            ci_workflow=ci_workflow,
            package_name="example_pkg",
            use_rust=True,
        )
    """
    parsed_ci_workflow = _parse_ci_workflow(ci_workflow)
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    lint_test = require_mapping(jobs, "lint-test", "CI workflow jobs")
    steps = require_sequence(lint_test, "steps", "CI lint-test job")
    assert _checkout_steps_disable_credentials(steps), (
        "expected CI checkout steps to disable credential persistence"
    )
    coverage_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == "Test and Measure Coverage"
    ]
    assert len(coverage_steps) == 1, "expected one shared coverage action step"
    coverage_step = coverage_steps[0]
    assert (
        coverage_step.get("uses")
        == "leynos/shared-actions/.github/actions/generate-coverage"
        "@d400b079fb6a8fa92f7e7b6c57f3d1c92a4b2d54"
    ), "expected CI to use the pinned shared coverage action"
    coverage_inputs = require_mapping(coverage_step, "with", "coverage step")
    assert coverage_inputs.get("output-path") == "coverage.xml", (
        "expected CI coverage output path to match the act assertion"
    )
    assert coverage_inputs.get("format") == "cobertura", (
        "expected CI coverage format to match the CodeScene upload"
    )
    assert coverage_inputs.get("artefact-name-suffix") == package_name.replace(
        "_", "-"
    ), "expected package-specific coverage artefact name suffix"
    if use_rust:
        assert coverage_inputs.get("cargo-manifest") == "rust_extension/Cargo.toml", (
            "expected Rust variant to pass the extension manifest to coverage"
        )
    else:
        assert "cargo-manifest" not in coverage_inputs, (
            "expected pure-Python variant to omit Rust coverage inputs"
        )


def _parse_ci_workflow(ci_workflow: str) -> dict[str, Any]:
    """Parse a generated CI workflow as a YAML mapping."""
    return parse_yaml_mapping(ci_workflow, "CI workflow")


def _assert_pyproject_contracts(
    *, package_name: str, pyproject: dict[str, Any], use_rust: bool
) -> None:
    """Assert generated Python packaging contracts."""
    project = require_mapping(pyproject, "project", "pyproject.toml")
    assert project.get("name"), "expected generated project metadata to include a name"
    assert project.get("requires-python") == ">=3.10", (
        "expected generated pyproject.toml to use the requested Python version"
    )
    dependency_groups = require_mapping(
        pyproject,
        "dependency-groups",
        "pyproject.toml",
    )
    dev_dependencies = dependency_groups.get("dev")
    assert isinstance(dev_dependencies, list), (
        "expected generated pyproject.toml to include a dev dependency group"
    )
    for dependency in ["pytest", "ruff", "pyright", "ty", "pytest-xdist"]:
        assert dependency in dev_dependencies, (
            f"expected generated dev dependencies to include {dependency}"
        )

    build_system = require_mapping(pyproject, "build-system", "pyproject.toml")
    if use_rust:
        assert build_system.get("build-backend") == "maturin", (
            "expected Rust variant to use maturin as the build backend"
        )
        maturin = require_mapping(pyproject, "tool", "pyproject.toml").get("maturin")
        assert isinstance(maturin, dict), (
            "expected Rust variant to include tool.maturin configuration"
        )
        assert maturin.get("manifest-path") == "rust_extension/Cargo.toml", (
            "expected Rust variant to point maturin at the extension manifest"
        )
        assert maturin.get("module-name") == f"{package_name}._{package_name}_rs", (
            "expected Rust variant to render the package-specific module name"
        )
    else:
        assert build_system.get("build-backend") == "hatchling.build", (
            "expected pure-Python variant to use hatchling as the build backend"
        )
        assert "maturin" not in pyproject.get("tool", {}), (
            "expected pure-Python variant to omit maturin configuration"
        )


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
            ("Makefile", f"ruff check {python_targets}"),
        ],
        "typecheck": [
            ("AGENTS.md", "ty check $(PYTHON_TARGETS)"),
            ("Makefile", f"ty check {python_targets}"),
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
            }
        )
    for target, checks in command_contracts.items():
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


def _parse_makefile_rules(makefile: str) -> dict[str, list[str]]:
    """Return generated Makefile rules parsed through make-parser."""
    target_names = set(
        re.findall(r"^([a-zA-Z][a-zA-Z_-]*):", makefile, flags=re.MULTILINE)
    )
    normalised_targets = {
        target: target.replace("-", "_") for target in target_names if "-" in target
    }

    def normalise_target(match: re.Match[str]) -> str:
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
    else:
        assert "lint-rust" not in makefile, (
            "expected pure-Python variant to omit Rust lint targets"
        )
        assert "TEST_CMD :=" not in makefile, (
            "expected pure-Python variant to omit Rust test command selection"
        )


def _assert_ci_workflow_contracts(
    *, parsed_ci_workflow: dict[str, Any], ci_workflow: str, use_rust: bool
) -> None:
    """Assert generated CI workflow contracts.

    Parameters
    ----------
    parsed_ci_workflow : dict[str, Any]
        Parsed generated CI workflow mapping.
    ci_workflow : str
        UTF-8 text of the generated CI workflow, used for string-level contract
        assertions.
    use_rust : bool
        Whether the rendered variant includes the optional Rust extension.
    """
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    lint_test = require_mapping(jobs, "lint-test", "CI workflow jobs")
    steps = require_sequence(lint_test, "steps", "CI lint-test job")
    assert _checkout_steps_disable_credentials(steps), (
        "expected generated CI workflow to disable checkout credentials"
    )
    assert "make check-fmt" in ci_workflow, (
        "expected generated CI workflow to run the formatting gate"
    )
    assert "make lint" in ci_workflow, (
        "expected generated CI workflow to run the lint gate"
    )
    assert "make typecheck" in ci_workflow, (
        "expected generated CI workflow to run the typecheck gate"
    )
    assert "make build" in ci_workflow, (
        "expected generated CI workflow to build the project before checks"
    )
    assert "leynos/shared-actions/.github/actions/generate-coverage" in ci_workflow, (
        "expected generated CI workflow to use the shared coverage action"
    )
    if use_rust:
        assert "leynos/shared-actions/.github/actions/setup-rust" in ci_workflow, (
            "expected Rust variant CI to set up Rust"
        )
        assert "Cache Rust lint and test tools" in ci_workflow, (
            "expected Rust variant CI to cache Rust tools"
        )
        assert "cargo-manifest: rust_extension/Cargo.toml" in ci_workflow, (
            "expected Rust variant CI to pass the Rust manifest to coverage"
        )
    else:
        assert "setup-rust" not in ci_workflow, (
            "expected pure-Python CI to omit Rust setup"
        )
        assert "cargo-manifest" not in ci_workflow, (
            "expected pure-Python CI to omit Rust coverage inputs"
        )


def _assert_release_workflow_contracts(
    *, release_workflow: str, use_rust: bool
) -> None:
    """Assert generated release workflow contracts."""
    parsed_release_workflow = parse_yaml_mapping(release_workflow, "release workflow")
    jobs = require_mapping(parsed_release_workflow, "jobs", "release workflow")
    release = require_mapping(jobs, "release", "release workflow jobs")
    release_steps = require_sequence(release, "steps", "release job")
    assert _checkout_steps_disable_credentials(release_steps), (
        "expected generated release workflow to disable checkout credentials"
    )
    assert "softprops/action-gh-release@v2" in release_workflow, (
        "expected release workflow to create a GitHub release"
    )
    assert "actions/download-artifact@v4" in release_workflow, (
        "expected release workflow to download wheel artefacts"
    )
    assert "--clobber" in release_workflow, (
        "expected release workflow to overwrite existing wheel assets on rerun"
    )
    if use_rust:
        assert "build-wheels" in jobs, (
            "expected Rust variant release workflow to build platform wheels"
        )
        build_wheels = require_mapping(jobs, "build-wheels", "release workflow jobs")
        assert build_wheels.get("uses") == "./.github/workflows/build-wheels.yml", (
            "expected Rust variant release workflow to call build-wheels.yml"
        )
        assert release.get("needs") == ["build-wheels"], (
            "expected Rust variant release job to wait for platform wheels"
        )
        assert "pure-wheel" not in jobs, (
            "expected Rust variant release workflow to skip pure wheel job"
        )
    else:
        assert "pure-wheel" in jobs, (
            "expected pure-Python release workflow to build one pure wheel"
        )
        assert release.get("needs") == ["pure-wheel"], (
            "expected pure-Python release job to wait for the pure wheel"
        )
        assert "build-wheels" not in jobs, (
            "expected pure-Python release workflow to skip platform wheel matrix"
        )


def _assert_wheel_workflow_contracts(
    *,
    build_wheels_workflow: str,
    build_wheels_action: str,
    pure_wheel_action: str,
) -> None:
    """Assert generated wheel workflow and action contracts."""
    parsed_build_wheels = parse_yaml_mapping(
        build_wheels_workflow,
        "build-wheels workflow",
    )
    build_jobs = require_mapping(parsed_build_wheels, "jobs", "build-wheels workflow")
    build_job = require_mapping(build_jobs, "build", "build-wheels workflow jobs")
    strategy = require_mapping(build_job, "strategy", "build-wheels build job")
    matrix = require_mapping(strategy, "matrix", "build-wheels strategy")
    includes = require_sequence(matrix, "include", "build-wheels matrix")
    assert len(includes) == 6, (
        "expected build-wheels workflow to cover Linux, Windows, and macOS"
    )
    assert "persist-credentials: false" in build_wheels_workflow, (
        "expected build-wheels workflow checkout to disable credentials"
    )
    assert "uvx --with 'cibuildwheel>=2.16.0,<4.0.0' cibuildwheel" in (
        build_wheels_action
    ), "expected Rust wheel action to build through cibuildwheel"
    assert "persist-credentials: false" in build_wheels_action, (
        "expected build-wheels action checkout to disable credentials"
    )
    assert "uv build --wheel" in pure_wheel_action, (
        "expected pure-wheel action to build through uv"
    )
    assert "persist-credentials: false" in pure_wheel_action, (
        "expected pure-wheel action checkout to disable credentials"
    )


def _checkout_steps_disable_credentials(steps: list[Any]) -> bool:
    """Return whether all checkout steps disable credential persistence."""
    checkout_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    return bool(checkout_steps) and all(
        isinstance(step.get("with"), dict)
        and step["with"].get("persist-credentials") is False
        for step in checkout_steps
    )
