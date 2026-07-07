"""Orchestrate rendered tooling contracts for generated project variants.

This module keeps the public test-helper API stable while delegating
domain-specific assertions to focused helper modules:
``pyproject_contracts``, ``agents_contracts``, ``makefile_contracts``,
``ci_contracts``, ``release_contracts``, and ``wheel_contracts``.  Top-level
template tests import from here, while each delegated module stays small enough
to own one contract domain.
"""

from __future__ import annotations

from typing import Any

from tests.helpers.agents_contracts import (
    _assert_agents_contracts,
    _assert_agents_make_targets_mirror_makefile,
)
from tests.helpers.ci_contracts import (
    _assert_act_validation_workflow_contracts,
    _assert_ci_workflow_contracts,
    _parse_ci_workflow,
    assert_ci_coverage_action_contract,
    assert_ci_python_matrix_contract,
)
from tests.helpers.makefile_contracts import (
    _assert_makefile_contracts,
    assert_common_make_targets,
)
from tests.helpers.pyproject_contracts import _assert_pyproject_contracts
from tests.helpers.release_contracts import _assert_release_workflow_contracts
from tests.helpers.wheel_contracts import _assert_wheel_workflow_contracts

__all__ = [
    "assert_ci_coverage_action_contract",
    "assert_ci_python_matrix_contract",
    "assert_common_make_targets",
    "assert_generated_tooling_contracts",
]


def assert_generated_tooling_contracts(
    *,
    package_name: str,
    agents: str,
    pyproject: dict[str, Any],
    makefile: str,
    ci_workflow: str,
    act_validation_workflow: str,
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
    act_validation_workflow : str
        UTF-8 text of the generated act-validation workflow.
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
            act_validation_workflow=act_validation_workflow,
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
    _assert_act_validation_workflow_contracts(
        act_validation_workflow=act_validation_workflow,
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
