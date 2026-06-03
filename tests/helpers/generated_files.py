"""Parse generated project files for template contract tests.

This module owns assertion-focused file reading and structured data parsing for
rendered Copier projects.  Rendering helpers use ``read_generated_text`` so
filesystem errors become pytest failures consistently, while tooling contract
helpers consume ``parse_yaml_mapping``, ``require_mapping``, and
``require_sequence`` to keep workflow schema checks readable.  Keep raw
generated-file I/O here so template tests share one error-reporting boundary.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml


def read_generated_text(path: Path) -> str:
    """Read a generated file with assertion-focused error context.

    Parameters
    ----------
    path
        Path to the generated file to read.

    Returns
    -------
    str
        UTF-8 decoded file contents.

    Raises
    ------
    pytest.fail.Exception
        Raised when the file cannot be read.

    Examples
    --------
    Read a rendered workflow before parsing it::

        workflow = read_generated_text(project / ".github/workflows/ci.yml")
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        pytest.fail(f"could not read generated file {path}: {error}")


def parse_toml_file(path: Path) -> dict[str, Any]:
    """Parse generated TOML with assertion-focused error context.

    Parameters
    ----------
    path
        Path to the generated TOML file.

    Returns
    -------
    dict[str, Any]
        Parsed TOML mapping.

    Raises
    ------
    pytest.fail.Exception
        Raised when the file cannot be read or the TOML is invalid.

    Examples
    --------
    Parse generated project metadata::

        pyproject = parse_toml_file(project / "pyproject.toml")
    """
    text = read_generated_text(path)
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        pytest.fail(f"could not parse generated TOML {path}: {error}")
    return parsed


def parse_yaml_mapping(text: str, label: str) -> dict[str, Any]:
    """Parse generated YAML as a mapping with clear failure context.

    Parameters
    ----------
    text
        YAML document text to parse.
    label
        Human-readable label used in assertion failure messages.

    Returns
    -------
    dict[str, Any]
        Parsed YAML mapping.

    Raises
    ------
    pytest.fail.Exception
        Raised when the YAML is invalid or the parsed document is not a mapping.

    Examples
    --------
    Parse a rendered CI workflow::

        workflow = parse_yaml_mapping(ci_workflow, "CI workflow")
    """
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as error:
        pytest.fail(f"could not parse generated {label}: {error}")
    if not isinstance(parsed, dict):
        pytest.fail(f"expected generated {label} to parse as a mapping")
    return parsed


def require_mapping(mapping: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    """Return a nested mapping or fail with the missing schema path.

    Parameters
    ----------
    mapping
        Parent mapping to inspect.
    key
        Nested key expected to contain a mapping.
    label
        Human-readable schema path used in assertion failure messages.

    Returns
    -------
    dict[str, Any]
        Nested mapping value.

    Raises
    ------
    pytest.fail.Exception
        Raised when the key is missing or the value is not a mapping.

    Examples
    --------
    Extract workflow jobs after parsing YAML::

        jobs = require_mapping(workflow, "jobs", "CI workflow")
    """
    value = mapping.get(key)
    if not isinstance(value, dict):
        pytest.fail(f"expected {label} to include mapping key {key!r}")
    return value


def require_sequence(mapping: dict[str, Any], key: str, label: str) -> list[Any]:
    """Return a nested sequence or fail with the missing schema path.

    Parameters
    ----------
    mapping
        Parent mapping to inspect.
    key
        Nested key expected to contain a sequence.
    label
        Human-readable schema path used in assertion failure messages.

    Returns
    -------
    list[Any]
        Nested sequence value.

    Raises
    ------
    pytest.fail.Exception
        Raised when the key is missing or the value is not a sequence.

    Examples
    --------
    Extract workflow steps from a parsed job::

        steps = require_sequence(job, "steps", "CI lint-test job")
    """
    value = mapping.get(key)
    if not isinstance(value, list):
        pytest.fail(f"expected {label} to include sequence key {key!r}")
    return value
