"""Assertion helpers for generated tooling and workflow contracts."""

from __future__ import annotations

from typing import Any

from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
)


def assert_common_make_targets(makefile: str) -> None:
    """Assert Makefile targets shared by all generated variants."""
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
    """Assert generated Python/Rust tooling contracts from one validator."""
    assert_pyproject_contracts(
        package_name=package_name,
        pyproject=pyproject,
        use_rust=use_rust,
    )
    assert_agents_contracts(agents)
    assert_makefile_contracts(makefile=makefile, use_rust=use_rust)
    assert_ci_workflow_contracts(ci_workflow=ci_workflow, use_rust=use_rust)
    assert_release_workflow_contracts(
        release_workflow=release_workflow,
        use_rust=use_rust,
    )
    assert_wheel_workflow_contracts(
        build_wheels_workflow=build_wheels_workflow,
        build_wheels_action=build_wheels_action,
        pure_wheel_action=pure_wheel_action,
    )


def assert_pyproject_contracts(
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


def assert_agents_contracts(agents: str) -> None:
    """Assert generated assistant guidance documents act-enabled testing."""
    assert "make test WITH_ACT=1" in agents, (
        "expected generated AGENTS.md to document act-enabled test runs"
    )
    assert "RUN_ACT_VALIDATION=1" in agents, (
        "expected generated AGENTS.md to describe the pytest act environment"
    )


def assert_makefile_contracts(*, makefile: str, use_rust: bool) -> None:
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


def assert_ci_workflow_contracts(*, ci_workflow: str, use_rust: bool) -> None:
    """Assert generated CI workflow contracts."""
    parsed_ci_workflow = parse_yaml_mapping(ci_workflow, "CI workflow")
    jobs = require_mapping(parsed_ci_workflow, "jobs", "CI workflow")
    lint_test = require_mapping(jobs, "lint-test", "CI workflow jobs")
    steps = require_sequence(lint_test, "steps", "CI lint-test job")
    assert checkout_steps_disable_credentials(steps), (
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


def assert_release_workflow_contracts(*, release_workflow: str, use_rust: bool) -> None:
    """Assert generated release workflow contracts."""
    parsed_release_workflow = parse_yaml_mapping(release_workflow, "release workflow")
    jobs = require_mapping(parsed_release_workflow, "jobs", "release workflow")
    release = require_mapping(jobs, "release", "release workflow jobs")
    release_steps = require_sequence(release, "steps", "release job")
    assert checkout_steps_disable_credentials(release_steps), (
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


def assert_wheel_workflow_contracts(
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


def checkout_steps_disable_credentials(steps: list[Any]) -> bool:
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
