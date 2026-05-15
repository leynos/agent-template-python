"""Pytest-copier configuration for this template."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def copier_template_paths() -> list[str]:
    """Copy only template sources into pytest-copier's temporary repository."""
    return ["copier.yml", "template"]
