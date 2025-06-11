#!/usr/bin/env bash
# Install tools needed to run tests for this template.
# These include the pytest-copier plugin and tooling for linting and type checking.
set -euo pipefail

pip install pytest-copier ruff pyright
