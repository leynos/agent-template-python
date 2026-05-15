# Generic Copier Template

This repository provides a [Copier](https://copier.readthedocs.io/) template for a Python package.
It offers two flavours:

1. **Python Only** – a pure Python implementation.
2. **Python with Rust** – includes a PyO3 extension.

Run `copier copy` and answer the prompts to generate a project.

## Running Tests

The test suite relies on the `pytest-copier` plugin and renders generated
projects that run Ruff, Pylint through the PyPy shim, `ty`, pytest, and, when the
Rust extension is enabled, Clippy, Whitaker, and nextest-aware Rust tests. Ensure
these tools are available before running `pytest`:

```bash
pip install pytest-copier
```

You can also run `scripts/setup_test_deps.sh` to install them automatically.
