"""Shared test utilities for rendered Copier template tests.

The helpers package groups reusable support code for tests that render Copier
projects and inspect their generated files.  It contains modules for generated
file parsing, rendered-project command execution, and tooling or workflow
contract assertions.  Fixtures remain in :mod:`tests.conftest`, while runtime
container helpers remain in :mod:`tests.utilities`.

Import helper functions from the module that owns their behaviour.  Test modules
may also import common helpers from ``tests.helpers`` when this package re-exports
them, but module-level imports keep ownership clearer for larger assertions.

Examples
--------
Use the generated-file and contract helpers in a template test::

    from tests.helpers.generated_files import parse_yaml_mapping
    from tests.helpers.tooling_contracts import assert_ci_coverage_action_contract

    workflow = parse_yaml_mapping(ci_workflow, "CI workflow")
    assert "jobs" in workflow
    assert_ci_coverage_action_contract(
        ci_workflow=ci_workflow,
        package_name="example_pkg",
        use_rust=False,
    )
"""
