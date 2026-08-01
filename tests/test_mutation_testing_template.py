"""Validate rendered mutation-testing configuration produced by the template.

This module covers the scheduled mutation-testing surface of generated
projects: the conditional rendering gates (a Python 3.13 or newer baseline for
mutmut, ``use_rust`` for cargo-mutants), the rendered documentation guidance,
the ``[tool.mutmut]`` packaging section, and the generated workflow's schedule,
permissions, concurrency, and shared-workflow job inputs.  It also pins the
Copier answer boundary that rejects malformed Python baseline versions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from pytest_copier.plugin import CopierFixture

from tests.helpers.generated_files import (
    parse_toml_file,
    parse_yaml_mapping,
    read_generated_text,
    require_mapping,
)
from tests.helpers.rendering import render_project

DEVELOPER_MUTATION_INTRO = """\
- `.github/workflows/mutation-testing.yml` runs daily at 09:30 UTC and supports
  manual dispatch. It delegates to reusable workflows from `leynos/shared-actions`;
  stagger the generated cron schedule before adopting it alongside other
  repositories."""
DEVELOPER_MUTMUT_GUIDANCE = """\
  The mutmut job is generated only when the minimum Python version is 3.13 or
  newer because the shared workflow helpers require Python 3.13 or newer."""
DEVELOPER_RUST_MUTATION_GUIDANCE = """\
  Rust-enabled projects also receive a cargo-mutants job for `rust_extension/`,
  independently of the Python version baseline."""
USER_MUTATION_INTRO = """\
## Scheduled Mutation Testing

The `.github/workflows/mutation-testing.yml` workflow runs mutation testing
daily at 09:30 UTC and can also be started manually from GitHub Actions. Adjust
the generated cron schedule to stagger it against other repositories."""
USER_MUTMUT_GUIDANCE_TEMPLATE = """\
For projects whose minimum Python version is 3.13 or newer, the workflow runs
mutmut against `{package_name}/`. The Python mutation job is omitted for
older baselines because the shared workflow helpers require Python 3.13 or
newer."""
USER_RUST_MUTATION_GUIDANCE = """\
Rust-enabled projects also run cargo-mutants against the crate in
`rust_extension/`, independently of the Python version baseline."""


def _rendered_section(text: str, *, start: str, end: str) -> str:
    """Return an optional rendered section with Jinja-only blank lines collapsed."""
    if start not in text:
        return ""
    section = text.partition(start)[2].partition(end)[0]
    return re.sub(r"\n{3,}", "\n\n", f"{start}{section}").strip()


def _assert_mutation_documentation(
    *,
    developer_guide: str,
    users_guide: str,
    expect_mutmut: bool,
    use_rust: bool,
    package_name: str,
) -> None:
    """Assert developer and user guidance matches the active mutation gates.

    The user guidance is package-specific, so ``package_name`` is interpolated
    into the expected text to pin the template's ``{{ package_name }}``
    substitution rather than a fixed package directory.
    """
    user_mutmut_guidance = USER_MUTMUT_GUIDANCE_TEMPLATE.format(
        package_name=package_name
    )
    expected_developer_guidance = "\n\n".join(
        section
        for section, enabled in (
            (DEVELOPER_MUTATION_INTRO, expect_mutmut or use_rust),
            (DEVELOPER_MUTMUT_GUIDANCE, expect_mutmut),
            (DEVELOPER_RUST_MUTATION_GUIDANCE, use_rust),
        )
        if enabled
    )
    expected_user_guidance = "\n\n".join(
        section
        for section, enabled in (
            (USER_MUTATION_INTRO, expect_mutmut or use_rust),
            (user_mutmut_guidance, expect_mutmut),
            (USER_RUST_MUTATION_GUIDANCE, use_rust),
        )
        if enabled
    )
    assert (
        _rendered_section(
            developer_guide,
            start="- `.github/workflows/mutation-testing.yml`",
            end="- `.github/actions/build-wheels`",
        )
        == expected_developer_guidance
    ), "expected developer mutation guidance to match the active mutation gates"
    assert (
        _rendered_section(
            users_guide,
            start="## Scheduled Mutation Testing",
            end="## Rust Test Behaviour",
        )
        == expected_user_guidance
    ), "expected user mutation guidance to match the active mutation gates"


def _assert_mutmut_pyproject_config(
    *, pyproject: dict[str, Any], package_name: str, expect_mutmut: bool
) -> None:
    """Assert ``[tool.mutmut]`` renders only for baselines of 3.13 or greater."""
    mutmut_config = pyproject.get("tool", {}).get("mutmut")
    if expect_mutmut:
        assert mutmut_config == {
            "source_paths": [f"{package_name}/"],
            "pytest_add_cli_args_test_selection": ["tests/"],
        }, "expected mutmut configuration for baselines of 3.13 or greater"
    else:
        assert mutmut_config is None, (
            "expected no mutmut configuration below a 3.13 baseline"
        )


def _assert_mutation_workflow_metadata(workflow: dict[str, Any]) -> None:
    """Assert the schedule, permissions, and concurrency shared by all callers."""
    # PyYAML parses the ``on:`` key as the boolean ``True``.
    triggers = workflow.get(True)
    assert isinstance(triggers, dict), (
        "expected the mutation workflow to declare on: triggers"
    )
    assert triggers.get("schedule") == [{"cron": "30 9 * * *"}], (
        "expected the mutation workflow to run daily at 09:30 UTC"
    )
    assert "workflow_dispatch" in triggers, (
        "expected the mutation workflow to allow manual dispatch"
    )
    assert workflow.get("permissions") == {}, (
        "expected the mutation workflow to default the token to no scopes"
    )
    concurrency = require_mapping(workflow, "concurrency", "mutation workflow")
    assert concurrency.get("group") == "mutation-testing-${{ github.ref }}", (
        "expected per-ref concurrency serialization for the mutation workflow"
    )
    assert concurrency.get("cancel-in-progress") is False, (
        "expected queued mutation runs to wait rather than cancel in progress"
    )


def _assert_mutation_job_gating(
    *,
    jobs: dict[str, Any],
    expect_mutmut: bool,
    use_rust: bool,
    package_name: str,
    python_version: str,
) -> None:
    """Assert job presence and shared-workflow inputs for the active gates."""
    assert ("mutation" in jobs) == expect_mutmut, (
        "expected the mutmut job only for baselines of 3.13 or greater"
    )
    assert ("mutation-rust" in jobs) == use_rust, (
        "expected the cargo-mutants job only for Rust variants"
    )
    if expect_mutmut:
        mutation_inputs = require_mapping(
            require_mapping(jobs, "mutation", "mutation workflow jobs"),
            "with",
            "mutmut job",
        )
        assert mutation_inputs.get("python-version") == python_version, (
            "expected the mutmut job to run on the project's baseline Python"
        )
        assert mutation_inputs.get("paths") == f"{package_name}/", (
            "expected the mutmut job to mutate the flat-layout package directory"
        )
        assert mutation_inputs.get("module-prefix-strip") == "", (
            "expected the mutmut job to strip no module prefix for a flat layout"
        )
    if use_rust:
        rust_inputs = require_mapping(
            require_mapping(jobs, "mutation-rust", "mutation workflow jobs"),
            "with",
            "cargo-mutants job",
        )
        assert rust_inputs.get("paths") == "", (
            "expected the cargo-mutants job to empty the root path list"
        )
        assert rust_inputs.get("extra-crate-dirs") == "rust_extension", (
            "expected the cargo-mutants job to target the extension crate directory"
        )
        assert rust_inputs.get("shard-count") == 1, (
            "expected the cargo-mutants job to confine the root target to one shard"
        )


def _assert_shared_workflow_shas(jobs: dict[str, Any]) -> None:
    """Assert every job pins its shared mutation workflow to a commit SHA."""
    expected_workflows = {
        "mutation": "mutation-mutmut.yml",
        "mutation-rust": "mutation-cargo.yml",
    }
    for job_name, job in jobs.items():
        uses = str(job.get("uses", "")) if isinstance(job, dict) else ""
        workflow_ref, separator, revision = uses.partition("@")
        assert workflow_ref == (
            f"leynos/shared-actions/.github/workflows/{expected_workflows[job_name]}"
        ), f"expected {job_name} to use its shared mutation workflow"
        assert separator == "@", (
            f"expected {job_name} shared mutation workflow reference to contain @"
        )
        assert re.fullmatch(r"[0-9a-f]{40}", revision), (
            f"expected {job_name} shared mutation workflow revision to be a "
            "40-character hexadecimal commit SHA"
        )


@pytest.mark.parametrize(
    ("target_dir", "use_rust", "python_version", "expect_mutmut", "package_name"),
    [
        ("mutation-312-pure", False, "3.12", False, "mutation_pkg"),
        ("mutation-312-rust", True, "3.12", False, "mutation_pkg"),
        # Render the enabled pure variant under a non-default package name so
        # the package-specific guidance, mutmut source paths, and workflow
        # inputs pin the template's substitution rather than a fixed directory.
        ("mutation-313-pure", False, "3.13", True, "custom_mutation_pkg"),
        ("mutation-314-rust", True, "3.14", True, "mutation_pkg"),
    ],
)
def test_generated_mutation_testing_gating(
    copier: CopierFixture,
    tmp_path: Path,
    target_dir: str,
    python_version: str,
    package_name: str,
    *,
    use_rust: bool,
    expect_mutmut: bool,
) -> None:
    """Rendered mutation testing follows the interpreter and Rust gates.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project is created.
    target_dir
        Temporary project directory name for the rendered variant.
    python_version
        Minimum supported Python version answer passed to Copier.
    package_name
        Package name answer passed to Copier. One enabled variant uses a
        non-default name so package-specific rendering is exercised.
    use_rust
        Whether the rendered variant includes the optional Rust extension.
    expect_mutmut
        Whether the baseline interpreter supports the mutmut workflow
        (3.13 or greater).

    Returns
    -------
    None
        The test passes when the mutmut job and ``[tool.mutmut]`` section
        render only for baselines of 3.13 or greater, the cargo-mutants job
        renders only with the Rust extension, the workflow file is absent when
        both gates are off, and the rendered schedule, permissions,
        concurrency, and shared-workflow job inputs match the template
        contract.
    """
    project = render_project(
        tmp_path / target_dir,
        copier,
        project_name="MutationProj",
        package_name=package_name,
        use_rust=use_rust,
        python_version=python_version,
    )
    _assert_mutation_documentation(
        developer_guide=read_generated_text(project / "docs" / "developers-guide.md"),
        users_guide=read_generated_text(project / "docs" / "users-guide.md"),
        expect_mutmut=expect_mutmut,
        use_rust=use_rust,
        package_name=package_name,
    )
    _assert_mutmut_pyproject_config(
        pyproject=parse_toml_file(project / "pyproject.toml"),
        package_name=package_name,
        expect_mutmut=expect_mutmut,
    )

    workflow_path = project / ".github" / "workflows" / "mutation-testing.yml"
    if not expect_mutmut and not use_rust:
        assert not workflow_path.exists(), (
            "expected no mutation workflow when both gates are off"
        )
        return
    workflow = parse_yaml_mapping(
        read_generated_text(workflow_path), "mutation workflow"
    )
    _assert_mutation_workflow_metadata(workflow)
    jobs = require_mapping(workflow, "jobs", "mutation workflow")
    _assert_mutation_job_gating(
        jobs=jobs,
        expect_mutmut=expect_mutmut,
        use_rust=use_rust,
        package_name=package_name,
        python_version=python_version,
    )
    _assert_shared_workflow_shas(jobs)


@settings(
    # Each example renders a full Copier project, so cap the run to keep CI
    # runtime predictable; the explicit ``@example`` cases still pin the
    # boundary minors (0, 12, 13, 14).
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(minor=st.integers(min_value=0, max_value=20))
@example(minor=0)
@example(minor=12)
@example(minor=13)
@example(minor=14)
def test_python_version_minor_controls_mutmut_generation(
    copier: CopierFixture,
    tmp_path_factory: pytest.TempPathFactory,
    minor: int,
) -> None:
    """Every valid Python 3 minor consistently controls mutmut generation.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path_factory
        Factory creating an isolated destination for every generated example.
    minor
        Generated Python minor version in the representative range 0 through
        20.

    Returns
    -------
    None
        The property holds when Python 3.13 and newer render the mutmut
        workflow job and configuration, while older minors render neither.

    Notes
    -----
    Hypothesis's function-scoped fixture health check is suppressed because
    ``pytest-copier`` supplies ``copier`` at function scope. Each example is
    isolated by a fresh destination from ``tmp_path_factory``.
    """
    project = render_project(
        tmp_path_factory.mktemp(f"mutation-property-{minor}"),
        copier,
        project_name=f"MutationProperty{minor}",
        package_name=f"mutation_property_{minor}",
        use_rust=False,
        python_version=f"3.{minor}",
    )
    workflow_path = project / ".github" / "workflows" / "mutation-testing.yml"
    pyproject = parse_toml_file(project / "pyproject.toml")
    mutmut_config = pyproject.get("tool", {}).get("mutmut")

    if minor >= 13:
        assert workflow_path.exists(), (
            "expected supported Python minor to render the mutation workflow"
        )
        workflow = parse_yaml_mapping(
            read_generated_text(workflow_path), "mutation workflow"
        )
        jobs = require_mapping(workflow, "jobs", "mutation workflow")
        assert "mutation" in jobs, (
            "expected supported Python minor to render the mutmut job"
        )
        assert mutmut_config is not None, (
            "expected supported Python minor to render [tool.mutmut]"
        )
    else:
        assert not workflow_path.exists(), (
            "expected unsupported Python minor to omit the mutation workflow"
        )
        assert mutmut_config is None, (
            "expected unsupported Python minor to omit [tool.mutmut]"
        )


@pytest.mark.parametrize("python_version", ["3", "three.13", "3.13.1", "4.0"])
def test_python_version_rejects_unexpected_formats(
    copier: CopierFixture,
    tmp_path: Path,
    python_version: str,
) -> None:
    """Reject malformed baseline versions at the Copier answer boundary.

    Parameters
    ----------
    copier
        ``pytest-copier`` fixture used to render the template.
    tmp_path
        Temporary directory where the rendered project would be created.
    python_version
        Invalid version answer supplied to Copier.

    Returns
    -------
    None
        The examples cover every rejected grammar shape: a missing minor,
        non-numeric components, an extra patch component, and a non-3 major.
        Copier reports the format error before evaluating dependent answers.
    """
    with pytest.raises(
        ValueError,
        match=r"Python version must use the 3\.X format",
    ):
        render_project(
            tmp_path / "invalid-python-version",
            copier,
            project_name="InvalidVersion",
            package_name="invalid_version",
            python_version=python_version,
        )
