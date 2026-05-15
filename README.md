# Generic Copier Template

This repository provides a [Copier](https://copier.readthedocs.io/) template for a Python package.
It offers two flavours:

1. **Python Only** – a pure Python implementation.
2. **Python with Rust** – includes a PyO3 extension.

Run `copier copy` and answer the prompts to generate a project.

## Running Tests

The test suite relies on the `pytest-copier` plugin and renders generated
projects that run Ruff, Pylint via a PyPy-backed runner, `ty`, pytest, and, when
the Rust extension is enabled, Clippy, Whitaker, and nextest-aware Rust tests.

Install the `pytest-copier` test dependency before running this repository's
`pytest` suite. Generated projects install and run their own tooling, including
Ruff, Pylint via PyPy, `ty`, pytest, and, when Rust is enabled, Clippy, Whitaker,
and nextest.

```bash
pip install pytest-copier
```

You can also run `scripts/setup_test_deps.sh` to install them automatically.
