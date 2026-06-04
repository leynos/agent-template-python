"""Validate rendered release workflow contracts.

Release workflow assertions live here to keep release-specific job wiring and
asset-upload checks separate from CI, Makefile, and wheel-action contracts.
The helper imports the shared checkout credential assertion from
``tests.helpers.ci_contracts``.
"""

from __future__ import annotations

from tests.helpers.ci_contracts import _checkout_steps_disable_credentials
from tests.helpers.generated_files import (
    parse_yaml_mapping,
    require_mapping,
    require_sequence,
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
