"""Check rendered projects track the generated ``typos.toml``.

The canonical ``AGENTS.md`` spelling block tells contributors to commit the
regenerated ``typos.toml``. A rendered project whose ignore rules list that
file would contradict its own instructions and force contributors to
force-add it, so the template must not ignore it.
"""

from __future__ import annotations

import subprocess
import typing as typ
from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.rendering import (
    initialize_git_repository,
    render_project,
    typos_toml_is_ignored,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENTS_BLOCK_START = "<!-- typos-config-builder:agents-md:start -->"
AGENTS_BLOCK_END = "<!-- typos-config-builder:agents-md:end -->"
COMMIT_INSTRUCTION = "commit the regenerated file"


class _FakeProject:
    """Stand in for a rendered project where only the path is read."""

    path = Path(".")


def _runner(returncode: int) -> typ.Callable[..., subprocess.CompletedProcess[bytes]]:
    """Return a process runner that exits with ``returncode``."""

    def run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        """Report the canned exit status for ``command``."""
        return subprocess.CompletedProcess(command, returncode)

    return run


@pytest.mark.parametrize("use_rust", [False, True], ids=["python-only", "rust"])
def test_rendered_project_does_not_ignore_typos_toml(
    copier: CopierFixture, tmp_path: Path, *, use_rust: bool
) -> None:
    """Assert Git would track ``typos.toml`` in a freshly rendered project.

    The check runs in a rendered project with a populated Git index, because
    ``git check-ignore`` reads the project's own ignore rules. Restoring the
    ``typos.toml`` line to ``template/.gitignore`` makes it fail.
    """
    project = render_project(
        tmp_path / "rendered",
        copier,
        project_name="Tracking",
        package_name="tracking_pkg",
        use_rust=use_rust,
    )
    initialize_git_repository(project)

    assert not typos_toml_is_ignored(project), (
        "typos.toml is regenerated and committed, so the template must not "
        "list it in .gitignore"
    )


def test_rendered_project_still_ignores_the_dictionary_cache(
    copier: CopierFixture, tmp_path: Path
) -> None:
    """Assert the untracked dictionary cache stays ignored.

    Only the generated configuration moved to being tracked; the local cache
    the builder keeps for offline runs must not be committed.
    """
    project = render_project(
        tmp_path / "rendered",
        copier,
        project_name="Tracking",
        package_name="tracking_pkg",
    )
    initialize_git_repository(project)

    ignored = project.run(
        "git check-ignore .typos-oxendict-base.toml .typos-oxendict-base.json"
    )

    assert ".typos-oxendict-base.toml" in ignored
    assert ".typos-oxendict-base.json" in ignored


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [(0, True), (1, False)],
    ids=["ignored", "not-ignored"],
)
def test_the_ignore_query_maps_git_exit_statuses(
    returncode: int, *, expected: bool
) -> None:
    """Assert exit status ``0`` reads as ignored and ``1`` as tracked."""
    project = typ.cast("typ.Any", _FakeProject())

    assert typos_toml_is_ignored(project, _runner(returncode)) is expected


def test_the_ignore_query_raises_on_a_git_failure() -> None:
    """Assert a fatal Git status is an error, not a silent "not ignored".

    Exit status ``128`` means Git could not evaluate the path (for example no
    repository), which must not read the same as a path Git would track.
    """
    project = typ.cast("typ.Any", _FakeProject())

    with pytest.raises(RuntimeError, match="exited with status 128"):
        typos_toml_is_ignored(project, _runner(128))


def test_the_ignore_query_raises_when_git_cannot_start() -> None:
    """Assert a process-start failure is reported as an error."""
    project = typ.cast("typ.Any", _FakeProject())

    def missing(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Fail as a missing executable does."""
        raise FileNotFoundError

    with pytest.raises(RuntimeError, match="could not start"):
        typos_toml_is_ignored(project, missing)


def test_the_parent_makefile_pins_the_v0_1_3_builder() -> None:
    """Assert the parent Makefile default and reference name the same tag."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.3" in makefile
    assert "typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_VERSION)" in makefile


@pytest.mark.parametrize("use_rust", [False, True], ids=["python-only", "rust"])
def test_rendered_agents_carries_the_canonical_spelling_block(
    copier: CopierFixture, tmp_path: Path, *, use_rust: bool
) -> None:
    """Assert the rendered AGENTS.md holds the marked block with its rule.

    The block must be delimited so a check can compare it with the release
    text, and it must carry the instruction to commit the regenerated file
    that the tracking policy depends on.
    """
    project = render_project(
        tmp_path / "rendered",
        copier,
        project_name="Tracking",
        package_name="tracking_pkg",
        use_rust=use_rust,
    )
    agents = (project.path / "AGENTS.md").read_text(encoding="utf-8")

    start = agents.index(AGENTS_BLOCK_START)
    end = agents.index(AGENTS_BLOCK_END)

    assert start < end
    assert COMMIT_INSTRUCTION in agents[start:end]
