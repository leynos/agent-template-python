#!/usr/bin/env bash
# Install tools needed to run tests for this template.
# Generated projects install their own linting and type-checking dependencies.
set -euo pipefail

pip install pytest-copier PyYAML syrupy
