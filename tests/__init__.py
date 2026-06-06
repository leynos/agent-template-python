"""Support utilities for the Copier template validation test suite.

The package exposes shared helpers and fixtures used by the repository tests,
including rendered-file parsers, generated-project command helpers, workflow
contract assertions, container runtime environment helpers, and pytest fixtures
loaded from :mod:`tests.conftest`.

Import the package directly when a test only needs package discovery, or import
specific utilities from their modules when using them in assertions. Importing
``tests`` has no side effects beyond normal package initialisation; runtime
probing for tools such as Docker, Podman, or ``act`` stays inside fixtures and
helper functions.

Examples
--------
Use helpers from the package in template tests::

    import tests
    from tests.helpers.generated_files import parse_yaml_mapping
    from tests.utilities import docker_environment

    assert tests.__doc__
    workflow = parse_yaml_mapping("name: CI\n", "workflow")
    env = docker_environment()
"""
