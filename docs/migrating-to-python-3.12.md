# Migrating generated projects to Python 3.12

The next applicable release of this template requires generated projects to
record a Python baseline of 3.12 or newer. Copier rejects a recorded
`python_version` below 3.12.

## Before updating the template

Check that the application, dependencies, and supported deployment environments
can run on the Python version you intend to record. Then update the existing
project's `python_version` answer in `.copier-answers.yml` to 3.12 or newer
before running `copier update`. Review the proposed Copier changes and resolve
conflicts while preserving project-specific code and configuration.

Changing the recorded baseline does not update deployed interpreters or runtime
configuration. Update those separately and test the application on the new
baseline.

## Validate the updated project

The generated `make all` gate runs build, formatting, lint, typechecking,
tests, and spelling. The expanded `lint` gate includes baseline and DF12
Pylint, Ruff and Interrogate, Ambrleaks, Skylos, Vulture, duplication
detection, and GitHub Actions validation. Rust-enabled projects also run their
Rust lint and test targets.

The `make lint-actions` target validates workflows and local actions and is
included in `make all`. Run `make markdownlint` separately to lint Markdown and
check repository-wide spelling.
