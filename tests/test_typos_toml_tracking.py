"""Check rendered projects track the generated ``typos.toml``.

The canonical ``AGENTS.md`` spelling block tells contributors to commit the
regenerated ``typos.toml``. A rendered project whose ignore rules list that
file would contradict its own instructions and force contributors to
force-add it, so the template must not ignore it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_copier.plugin import CopierFixture

from tests.helpers.rendering import (
    initialize_git_repository,
    render_project,
    typos_toml_is_ignored,
)


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
