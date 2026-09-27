---
title: Maturin and PyO3 validation design
status: Draft
audience: Template maintainers and implementers applying Rust-extension
  validation to generated repositories
date: 2026-06-14
---

# Maturin and PyO3 validation design

## Problem statement

The Python template can render projects that include a Rust extension built
with PyO3 and maturin. A maturin or PyO3 upgrade can succeed at dependency
resolution while silently changing the built wheel: the native module path, the
`WHEEL` generator, `Root-Is-Purelib`, Python metadata, Software Bill of
Materials (SBOM) entries, or platform tags can drift. A PyO3 upgrade can also
change binding APIs or link behaviour enough that `cargo test` and `maturin
build` need different feature and environment settings.

The template needs a validation design that generated Rust-extension projects
can adopt without affecting pure-Python renders. The design must make upgrade
failures local, visible, and specific: maintainers should change a small set of
version pins and receive a failing assertion that names the broken packaging or
PyO3 contract.

## Evidence

The design is based on five ley-nos repositories and the current upstream
packaging guidance.

| Source | Relevant approach | Design consequence |
| --- | --- | --- |
| `leynos/prosidy-darn`, branch `test/maturin-pyo3-test-upgrade` | Pins `maturin==1.13.3` in the dev group and build backend, pins PyO3 `0.28.3`, tests maturin pin synchronisation across `pyproject.toml`, the reusable `build-wheels.yml` workflow, and the wheel composite action, tests PyO3 manifest/lockfile parity, builds one native wheel, and compares normalised wheel metadata and entries. Its main CI runs ordinary Make gates and coverage; its tag release workflow calls the reusable wheel workflow and uploads wheel artefacts to the GitHub release. | The template should generate a compatibility helper and focused pytest module for Rust projects. The helper should parse TOML structurally where possible and normalise platform-specific wheel entries before comparison. CI validation must distinguish the main quality-gate workflow from the release wheel-production workflow. |
| `leynos/cuprum` | Uses a richer helper for wheel snapshots, synchronises maturin pins across `pyproject.toml`, `.github/workflows/build-wheels.yml`, and `.github/actions/build-wheels/action.yml`, pins an aarch64 manylinux container, builds pure and native wheels, then installs pure followed by native wheels to verify the availability probe changes from `False` to `True`. | Native-wheel validation should not stop at `maturin build`. The release workflow should prove that pure and native wheels can coexist and that the Python API detects the native extension accurately. |
| `leynos/tei-rapporteur` | Uses a workspace crate with `cdylib` and `rlib`, separate `auto-initialize` and `extension-module` features, `pyo3-build-config` with `resolve-config`, a build script that only emits extension-module link args when `TEI_PY_BUILD_EXTENSION` or `MATURIN_BUILDING` is set, and pytest wheel snapshot checks. | The template must account for repositories where Rust tests need Python embedding while wheel builds need extension-module linking. The validation contract should allow an optional project-specific wheel-build environment variable. |
| `leynos/stilyagi` | Pins maturin in the dev group and build backend, builds the wheel with `--interpreter sys.executable`, snapshots wheel metadata with syrupy, includes malformed-input tests for the maturin helpers, and adds `trybuild` compile-pass/compile-fail tests for PyO3 module signatures and `py.detach`. | The template should pass the active pytest interpreter to local maturin builds and should document compile-time PyO3 UI tests as the right escalation for non-trivial bridge APIs. |
| `leynos/femtologging` | Uses maturin and PyO3 heavily, but keeps maturin ranges broad in `pyproject.toml`, enables extension-related defaults in the crate, and relies on build/test lanes rather than explicit pin and wheel-layout assertions. | The absence of pin synchronisation and wheel metadata checks is a useful negative case: broad version ranges and successful `maturin develop` are not enough to validate an upgrade. |
| Maturin user guide and repository | Maturin is configured through `pyproject.toml`, builds distributable wheels with `maturin build`, supports mixed Rust/Python layouts through `python-source` and `module-name`, and requires manylinux-aware builds for widely usable Linux wheels. The upstream repository showed maturin `v1.14.0` as latest on 2026-06-14. | The template should treat the maturin version as a single pinned template variable, not bake in the older pins observed in downstream repos. |
| PyO3 build and distribution guide | PyO3 build configuration is driven by `pyo3-build-config`; `PYO3_BUILD_EXTENSION_MODULE` is required for extension-module builds and is set by maturin; extension-module linking is different from test/embedding linking; `abi3` and `abi3t` reduce Python-version wheel count but restrict API use. The current guide examples use PyO3 `0.29.0`. | The template must separate the wheel-build mode from Rust test mode and should make `abi3` or `abi3t` an explicit future decision rather than an accidental default. |
| Python wheel specification | A wheel is a ZIP archive containing `.dist-info/METADATA`, `.dist-info/WHEEL`, and `.dist-info/RECORD`; `Root-Is-Purelib` controls purelib versus platlib installation; compatibility tags encode interpreter, ABI, and platform compatibility. | The generated test should inspect the wheel archive directly instead of relying only on a successful build command. |

## Goals

- Render no maturin or PyO3 validation files for pure-Python projects.
- Render a single-source maturin pin for Rust-extension projects and assert
  that every generated packaging and CI surface uses it.
- Render a PyO3 version contract that checks the Rust manifest and lockfile
  agree after dependency upgrades.
- Build one local native wheel in pytest when the Rust toolchain and maturin
  are available.
- Snapshot the native wheel's normalised metadata and entry layout so packaging
  drift fails at review time.
- Keep local Rust tests and release wheel builds from fighting over PyO3
  extension-module linking.
- Support both simple single-crate extensions and workspace-style extension
  crates.

## Non-goals

- The template will not guarantee that every generated repository publishes
  every platform wheel. CI matrix design remains repository-specific.
- The template will not choose `abi3` or `abi3t` by default. Stable ABI support
  changes PyO3 API availability and performance trade-offs, so repositories
  must opt in deliberately.
- The template will not replace full GitHub Actions validation with local
  pytest. Local wheel snapshot checks catch contract drift; cross-platform
  wheel production still belongs in CI.
- The template will not make pure-Python renders carry maturin, PyO3, Cargo,
  or wheel-action dependencies.

## Design intent

Generated Rust-extension projects should treat maturin and PyO3 upgrades as a
packaging contract change, not a normal dependency bump. The contract has three
layers: version pins agree, the active toolchain matches the pins when present,
and a built wheel has the expected metadata and native module layout.

| Layer | Invariants it owns |
| --- | --- |
| Pin layer | Pure-Python renders omit maturin and PyO3; Rust-extension renders repeat exactly one maturin pin; PyO3 source and lockfile agree. |
| Toolchain layer | The active maturin module matches the selected pin when present; local wheel builds use the pytest interpreter; unsupported interpreter combinations skip with named reasons. |
| Artefact layer | A local native wheel is a platform wheel produced by the pinned maturin version; focused assertions name generator, `Root-Is-Purelib`, and native-module failures; the snapshot catches remaining layout drift; release artefacts come from the reusable wheel workflow. |

## Terminology

| Term | Definition |
| --- | --- |
| Rust-extension project | A generated project rendered with `use_rust=true`. |
| Pure-Python project | A generated project rendered with `use_rust=false`. |
| Native wheel | A wheel containing the PyO3 extension module. Its `WHEEL` metadata should report `Root-Is-Purelib: false`. |
| Pure wheel | A wheel containing only Python files. It is useful in projects like Cuprum that publish a fallback package. |
| Pin surface | A file that repeats the selected maturin version, such as `pyproject.toml`, a workflow `env`, or a composite action input default. |
| Wheel snapshot | A normalised dictionary derived from the built wheel's `METADATA`, `WHEEL`, and archive member names. |

## Generated surfaces

The template should add the following files only when `use_rust` is true.

| Surface | Purpose |
| --- | --- |
| `tests/helpers/maturin.py.jinja` | Shared compatibility helpers for pin parsing, toolchain detection, wheel building, and wheel snapshot normalisation. |
| `tests/test_maturin_build.py.jinja` | Focused pytest contract tests for maturin pin synchronisation, active maturin version, PyO3 lockfile parity, and native wheel layout. |
| `template/pyproject.toml.jinja` Rust branch | Adds pinned `maturin=={{ maturin_version }}` to the dev group and build backend, plus `[tool.maturin]` settings for `manifest-path`, `module-name`, `python-source`, `bindings`, and feature selection. |
| `template/.github/workflows/build-wheels.yml` | Exposes `MATURIN_VERSION` once and passes it to the generated wheel action. |
| `template/.github/actions/build-wheels/action.yml` | Installs or invokes the exact maturin version passed by the workflow. |
| `template/.github/workflows/ci.yml.jinja` | Runs the ordinary generated Make gates and should execute the generated maturin compatibility pytest module through `make test`; it should not own the cross-platform wheel matrix. |
| `template/.github/workflows/release.yml.jinja` | Calls the reusable wheel workflow for Rust-extension releases and publishes only the artefacts produced by that workflow. |
| `template/docs/rust-extension.md` | Documents the validation contract and how to update pins intentionally. |

Pure-Python renders must continue to assert that `pyproject.toml` contains no
`tool.maturin` configuration and no maturin dependency. Existing template tests
already enforce that boundary and should be extended rather than replaced.
Rust-extension parent-template tests should also assert the opposite of the
femtologging negative case: the rendered project must not use a broad maturin
range, and CI must not rely only on a successful `maturin develop` command as
its validation of the extension build.

## Template variables

The generated validation needs explicit template answers or defaults.

| Variable | Default | Used by |
| --- | --- | --- |
| `maturin_version` | Current upstream version when this design is implemented | `pyproject.toml`, wheel workflow, wheel action, tests |
| `pyo3_version` | Current upstream version when this design is implemented | `rust_extension/Cargo.toml`, PyO3 parity test |
| `rust_extension_crate_dir` | `rust_extension` | `tool.maturin.manifest-path`, pytest wheel build helper, CI coverage input |
| `rust_extension_module_name` | `_{package_name}_rs` | `[lib].name`, `tool.maturin.module-name`, wheel entry normaliser |
| `maturin_build_env_var` | empty | Optional TEI-style switch for repositories that separate test and wheel link modes |
| `maturin_features` | project default features | `tool.maturin.features`, local wheel build command |
| `enable_pyo3_ui_tests` | `false` | Optional `trybuild` tests for repositories with a non-trivial PyO3 bridge |
| `expects_sbom` | `false` | Whether the expected wheel entry set includes a normalised SBOM entry |

The implementation can start with constants in the rendered files and promote
them to Copier answers only when a generated repository needs to override them.
The important invariant is that the rendered project has one value per pin and
tests assert every repeated surface matches that value.

An empty `maturin_build_env_var` means the helper sets no project-specific
environment variable. In that mode, maturin's own `MATURIN_BUILDING` signal is
the only wheel-build signal.

## Version pin contract

The generated tests should parse pins from structured files where practical.
`pyproject.toml` and `Cargo.lock` should use `tomllib`. YAML workflows can use
existing repository helpers when tests run in the template parent. Rendered
project tests should stay dependency-light; they may use focused regular
expressions for YAML only, with assertion messages naming the source file and
field. TOML and wheel metadata must use structured parsing.

### Version comparison

Generated projects should canonicalise tool versions before comparison.

| Version source | Canonical form | Matching rule |
| --- | --- | --- |
| `maturin==X.Y.Z` in `pyproject.toml` | `(X, Y, Z)` integer tuple parsed from the exact dependency pin | Exact match. Broad ranges such as `maturin>=1.13,<2` fail the template contract because upgrades must be deliberate. |
| `MATURIN_VERSION: "X.Y.Z"` in YAML | `(X, Y, Z)` integer tuple parsed from the scalar value | Exact match against the `pyproject.toml` maturin pin. |
| Installed maturin | Prefer `importlib.metadata.version("maturin")`; if the CLI is inspected, strip a leading `maturin` token and parse the first `X.Y.Z` token | Exact match against the `pyproject.toml` maturin pin. Local absence skips the active-toolchain test only. |
| PyO3 manifest dependency | Full `X.Y.Z` version tuple from `Cargo.toml` | Exact match for generated projects. The template should emit a full patch version, not `0.28` or a range. |
| PyO3 lockfile package | Full `X.Y.Z` version tuple from `Cargo.lock` | Exact match against the generated PyO3 manifest version. |

Existing downstream repositories may temporarily use a minor-only PyO3 manifest
such as `0.28` while `Cargo.lock` resolves `0.28.3`. That is
prefix-compatible for Cargo, but it is not the generated-template contract. A
repository migration may accept the prefix during the first import only if the
same change replaces it with a full patch pin before declaring the validation
complete.

The minimum Rust-extension pin contract is:

| Contract | Failure message should name |
| --- | --- |
| `pyproject.toml` dev dependency contains exactly one `maturin==X.Y.Z` pin. | `pyproject.toml` dev dependency pin |
| `build-system.requires` contains the same `maturin==X.Y.Z` pin for direct maturin build-backend projects. | `pyproject.toml` build-system pin |
| `.github/workflows/build-wheels.yml` exposes the same `MATURIN_VERSION`. | workflow environment pin |
| `.github/actions/build-wheels/action.yml` defaults to or installs the same maturin version. | composite action pin |
| `.github/workflows/release.yml` depends on the reusable wheel workflow for Rust-extension releases. | release wheel-production path |
| `Cargo.toml` PyO3 dependency version equals the expected PyO3 version. | Rust manifest PyO3 pin |
| `Cargo.lock` PyO3 package version equals the expected PyO3 version. | Rust lockfile PyO3 package |

If a generated repository has no separate build-wheels workflow, the helper
should accept a repository-specific list of pin surfaces instead of requiring
Cuprum's exact workflow shape. TEI Rapporteur validates against `ci.yml`; the
template should keep that flexibility by storing pin locations in helper
constants near the package-specific names.

## Wheel build contract

The generated pytest module should build a single local native wheel when all
required tools are present:

```python
command = [
    sys.executable,
    "-m",
    "maturin",
    "build",
    "--release",
    "--interpreter",
    sys.executable,
    "--out",
    str(out_dir),
    "--manifest-path",
    str(root / "rust_extension/Cargo.toml"),
]
```

The local wheel contract is not a fast unit-test lane. `maturin build
--release` can compile and link Rust code on every Rust-extension CI run. The
default design keeps `--release` to match the produced artefact path. Projects
whose extension build exceeds their CI budget should keep the static pin tests
in the default suite and move the wheel build test behind a named pytest marker
or a separate `make test-wheel` target that the main CI still runs before
merge.

The helper must pass `--interpreter sys.executable`. Stilyagi needed this
because maturin could not discover `python3` inside the uv-managed Python
environment during the first snapshot run; the test should validate the
interpreter running pytest, not an ambient interpreter found on `PATH`.

The test must skip, not fail, when `cargo`, `rustc`, or a runnable
`python -m maturin` are unavailable. It should also skip Python interpreters
known to be unsupported by the pinned maturin version. The Prosidy and TEI
tests currently skip Python 3.15 for maturin `1.13.3`; the generated helper
should express this as a compatibility table keyed by the maturin pin, not as a
permanent Python-version rule.

Skips must be explicit and auditable:

- Missing `cargo`, `rustc`, or maturin skips with the missing tool named in the
  pytest skip message.
- Unsupported Python/maturin combinations skip with a message naming the
  active Python version and maturin pin.
- Active maturin version mismatch skips the wheel-build fixture and fails the
  installed-version test when maturin is installed but does not match the pin.
- Parent-template tests assert that the rendered helper contains a
  pin-keyed compatibility table and non-empty skip reasons for each skip path.

When a project needs a wheel-build signal, the helper should copy
`os.environ`, set the project-specific environment variable to `1`, and rely on
maturin's own `MATURIN_BUILDING` signal when no extra variable is configured.
That covers TEI's build-script pattern without forcing every generated crate to
carry a custom build script.

## Wheel snapshot contract

The helper should inspect the built wheel as a ZIP archive and return a stable
snapshot with four fields:

| Field | Source | Normalisation |
| --- | --- | --- |
| `generator` | `WHEEL` `Generator: maturin (X.Y.Z)` header | Keep only the version string and assert it equals the expected pin. |
| `metadata` | `METADATA` headers | Preserve `Name`, `Version`, `Requires-Python`, sorted `Requires-Dist`, and sorted classifiers when present. |
| `wheel` | `WHEEL` headers | Preserve `Root-Is-Purelib`; normalise `Tag` to `<platform-tag>` unless the repository deliberately validates ABI tags. |
| `entries` | ZIP member names | Replace versioned `.dist-info` directories, SBOM names, and native extension suffixes with placeholders. |

The test should make focused assertions before comparing the catch-all
snapshot:

| Assertion | Named failure |
| --- | --- |
| `snapshot["generator"] == expected_maturin_version` | The wheel was not produced by the pinned maturin version. |
| `snapshot["wheel"]["root_is_purelib"] == "false"` | The native wheel was built as a pure wheel. |
| Exactly one normalised native extension entry exists. | The PyO3 module is missing, duplicated, or installed under the wrong package path. |

The full snapshot remains useful as a catch-all for metadata and layout drift,
but the focused assertions satisfy the requirement that operationally important
failures name the broken contract.

The expected snapshot for the generated default Rust extension should include:

```python
{
    "generator": EXPECTED_MATURIN_VERSION,
    "metadata": {
        "name": PROJECT_NAME,
        "version": "0.1.0",
        "requires_python": f">={PYTHON_VERSION}",
        "requires_dist": [],
    },
    "wheel": {
        "root_is_purelib": "false",
        "tag": "<platform-tag>",
    },
    "entries": [
        f"{PACKAGE_NAME}-<version>.dist-info/METADATA",
        f"{PACKAGE_NAME}-<version>.dist-info/RECORD",
        f"{PACKAGE_NAME}-<version>.dist-info/WHEEL",
        f"{PACKAGE_NAME}-<version>.dist-info/licenses/LICENSE",
        f"{PACKAGE_NAME}/__init__.py",
        f"{PACKAGE_NAME}/pure.py",
        f"{PACKAGE_NAME}/{RUST_EXTENSION_MODULE_NAME}.cpython-<platform>.<extension>",
    ],
}
```

Generated repositories that emit SBOMs should include a normalised
`<sbom>.cyclonedx.json` entry only when `expects_sbom` is true. The expected
snapshot is a regenerated artefact of the rendered package contract, not a
frozen literal. Legitimate changes to runtime dependencies, package version,
classifiers, SBOM output, or package files should update the expected snapshot
in the same commit as the intentional packaging change.

The `requires_dist` and package `version` fields are expected-drift fields.
They should still appear in the snapshot because dependency and version drift
matter to release reviewers; they should not be treated as constants that every
future generated repository must keep empty or at `0.1.0`.

## PyO3 feature and link-mode contract

The generated default crate can keep the simple PyO3 shape:

```toml
[lib]
name = "_{{ package_name }}_rs"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "{{ pyo3_version }}", features = ["extension-module"] }
```

This is enough for the template's current minimal extension. Repositories with
Rust tests that embed Python or with workspace crates should use the TEI
pattern instead:

```toml
[lib]
crate-type = ["cdylib", "rlib"]

[features]
default = ["auto-initialize"]
auto-initialize = ["pyo3/auto-initialize"]
extension-module = ["pyo3/extension-module"]

[build-dependencies]
pyo3-build-config = { version = "{{ pyo3_version }}", features = ["resolve-config"] }
```

Their build script should call `pyo3_build_config::use_pyo3_cfgs()` and add
extension-module link arguments only when a wheel-build signal is present. This
separation is necessary because PyO3's extension-module mode disables
`libpython` linking for Unix wheel compliance, while Rust tests and examples
often need embedding-style linking.

The template should document this as an escalation path rather than make every
generated project carry the more complex workspace pattern.

## PyO3 compile-time contract

Runtime Python tests prove that a built extension imports and executes.
Stilyagi shows a separate failure class: PyO3 macro and API compatibility can
drift before a runtime import exists. Its `trybuild` suite validates two
compile-pass cases and three compile-fail cases:

| Case | Contract |
| --- | --- |
| Well-formed `#[pymodule]` | A module function returning `PyResult<()>` and registering `#[pyfunction]` exports still compiles. |
| `py.detach(...)` | Rust work can run outside the Python attachment and return to Python-owned objects afterwards. |
| Bad second `#[pymodule]` argument | PyO3 rejects a module function whose module parameter is not `&Bound<'_, PyModule>`. |
| Bad `#[pymodule]` return type | PyO3 rejects a module function that does not return `PyResult<()>`. |
| Extra `#[pymodule]` argument | PyO3 rejects arity drift in the module initialiser. |

The generated starter extension does not need these tests because its PyO3
surface is one `hello()` function. Repositories that add real bridge code
should enable `trybuild`, keep UI fixtures beside the extension crate, and
commit `.stderr` files for compile-fail diagnostics. When a PyO3 upgrade
changes diagnostics intentionally, maintainers refresh those `.stderr` files in
the same commit as the version bump.

If a repository opts into `abi3` or `abi3t`, the wheel snapshot and
cross-platform matrix must change together. The expected wheel tag moves from a
single interpreter-specific tag such as `cp314-cp314-<platform>` to a stable ABI
tag such as `cp38-abi3-<platform>` or `cp315-abi3t-<platform>`, and fewer
per-interpreter builds may be needed. That choice belongs in the repository's
Rust-extension documentation before the feature flag lands.

## Rust-extension runbook

The generated `docs/rust-extension.md` file is the maintainer runbook for this
contract. It must contain:

- the maturin pin surfaces that must change together;
- the PyO3 manifest and lockfile surfaces that must change together;
- the focused command for refreshing the wheel snapshot;
- the expected local and CI gates after an upgrade;
- the rule for `--interpreter sys.executable`;
- the skip semantics for missing tools and unsupported interpreters;
- the TEI-style feature/build-script escalation trigger for repositories whose
  Rust tests need Python embedding;
- the `trybuild` escalation trigger for non-trivial PyO3 bridge APIs;
- the `abi3` or `abi3t` opt-in warning and expected tag change;
- the SBOM expectation flag and when to update it.

## CI and release validation

The generated CI should keep local checks and platform production checks
separate.

| Lane | Required behaviour |
| --- | --- |
| Main CI | Runs `make check-fmt`, `make lint`, `make typecheck`, `make audit`, and `make test`. For Rust-extension renders, `make test` includes static maturin compatibility tests and, unless the project moves it to a named marker or `make test-wheel`, the local wheel build contract. This lane proves the repository's ordinary quality gates and local wheel contract, not the full platform matrix. |
| Coverage lane | Measures coverage from the installed/generated project and uploads the coverage artefact. Prosidy Darn keeps CodeScene upload separate from wheel production; the template should preserve that separation. |
| Reusable wheel workflow | Builds native wheels with the pinned maturin version on the configured platform matrix. Prosidy Darn uses `cibuildwheel`, installs Rust inside Linux builders with `CIBW_BEFORE_ALL_LINUX`, uses QEMU for non-`x86_64` Linux builds, and passes `MATURIN_VERSION` from workflow `env` into the composite action. |
| Release workflow | Runs on version tags, calls the reusable wheel workflow with the project Python version, downloads wheel artefacts, and uploads only those artefacts to the release. |
| Optional install verification | Installs pure and native wheels in a temporary directory and checks the package imports away from the repository checkout. |

Cuprum's pure-then-native install check should be templated only for projects
that publish both pure and native wheels. The default generated Rust-extension
project currently has one native wheel path, so its minimum CI smoke test is
`pip install <wheel>` followed by an import from a temporary directory.

## Failure modes

| Failure | Detection |
| --- | --- |
| Maturin upgraded in `pyproject.toml` but not in CI. | `test_maturin_pins_are_synchronised` fails with the pin map. |
| Maturin CLI in the active environment is stale. | `test_installed_maturin_matches_expected_pin` fails or skips if maturin is absent. |
| PyO3 manifest upgraded but lockfile not refreshed. | `test_pyo3_pin_matches_lockfile` fails with manifest and lockfile versions. |
| `maturin build` succeeds but native module path changes. | The focused native-entry assertion fails before the full wheel snapshot diff. |
| Wheel accidentally becomes pure. | The focused `Root-Is-Purelib: false` assertion fails. |
| Package metadata drifts during build-backend upgrade. | Snapshot compares `Name`, `Version`, `Requires-Python`, and dependency headers. |
| Rust tests fail because extension-module linking disabled `libpython`. | Repository should switch to the TEI feature/build-script pattern and keep wheel-build signalling explicit. |
| Maturin uses the wrong Python interpreter in a uv-managed environment. | The wheel helper passes `--interpreter sys.executable`, tying the build to the interpreter running pytest. |
| PyO3 macro compatibility drifts without a runtime import failure. | Optional `trybuild` UI tests fail in the extension crate. |
| The local wheel test silently skips in CI. | Parent-template tests require pin-keyed compatibility data and named skip messages; CI logs expose the skip reason. |
| SBOM output appears or disappears. | The snapshot changes, and `expects_sbom` records whether that drift is expected. |
| CI cross-compilation diverges from local wheel build. | Workflow contract tests assert the pinned maturin version and platform-specific container references where configured. |
| Main CI passes but release wheels cannot build. | The release workflow must depend on the reusable wheel workflow; parent-template workflow contract tests should assert that Rust-extension release workflows route through wheel production before upload. |

## Verification strategy

The design has seven named invariants.

| Layer | Invariant | Verification method |
| --- | --- | --- |
| Pin | Pure-Python renders do not mention maturin or PyO3. | Existing parent-template pytest assertions over rendered `pyproject.toml`, generated docs, and Makefile targets. |
| Pin | Every Rust-extension render repeats exactly one maturin pin across configured pin surfaces. | Generated pytest reads the pin map and asserts `len(set(pins.values())) == 1`. Parent-template tests assert the rendered surfaces contain the templated pin. |
| Pin | PyO3 source and lockfile agree after dependency upgrades. | Generated pytest parses the Rust manifest and lockfile with `tomllib` and applies the version-comparison rule. |
| Toolchain | A local native wheel is a platform wheel produced by the pinned maturin version. | Generated pytest builds one wheel when the toolchain is available; skip paths carry named reasons and compatibility data is pin-keyed. |
| Artefact | Wheel layout drift is intentional. | Generated pytest runs focused generator, purelib, and native-entry assertions, then compares the normalised wheel snapshot. Snapshot updates must accompany intentional packaging changes. |
| Toolchain | Non-trivial PyO3 bridge signatures remain compatible with the pinned PyO3 family. | Optional `trybuild` compile-pass and compile-fail fixtures validate selected bridge patterns. |
| Artefact | Release artefacts come from the same wheel workflow that carries the maturin pin. | Parent-template workflow contract tests parse the rendered release workflow and assert its `native-wheels` job calls `./.github/workflows/build-wheels.yml` before upload. |

The tests intentionally do not prove cross-platform wheel installability. That
property depends on GitHub-hosted runners, manylinux images, Windows/macOS
toolchains, and optional cross-compilation containers. CI workflow and release
workflow tests must cover that surface separately.

## Implementation sequence

1. Add `maturin_version` and `pyo3_version` defaults to `copier.yml`.
2. Update the Rust branch of `template/pyproject.toml.jinja` to pin maturin in
   `dependency-groups.dev`, `[build-system]`, and `[tool.maturin]`.
3. Update `template/{% if use_rust %}rust_extension{% endif %}/Cargo.toml.jinja`
   to use the templated PyO3 version.
4. Add rendered `tests/helpers/maturin.py.jinja` and
   `tests/test_maturin_build.py.jinja`.
5. Add version canonicalisation helpers for exact maturin and PyO3 patch pins.
6. Pass `--interpreter sys.executable` from the wheel-build helper so the
   local compatibility test uses the active pytest interpreter.
7. Add named skip messages and a pin-keyed compatibility table for
   maturin/Python support.
8. Add focused wheel assertions for generator version, `Root-Is-Purelib`, and
   native-module entry presence before the full snapshot comparison.
9. Extend parent-template contract tests to assert pure-Python omission and
   Rust-extension inclusion of the new files, pins, and Makefile/CI commands.
10. Assert parent-template regressions against broad maturin ranges and bare
    `maturin develop` validation.
11. Update `template/.github/workflows/build-wheels.yml` and
   `template/.github/actions/build-wheels/action.yml` to pass a single
   `MATURIN_VERSION`.
12. Extend release-workflow contract tests so Rust-extension releases depend on
   the reusable wheel workflow before publishing release artefacts.
13. Expand `template/docs/rust-extension.md` with the required runbook
   sections listed above.
14. Document optional `trybuild` PyO3 UI tests for repositories whose bridge
   surface grows beyond the starter function.
15. Refresh generated snapshots with syrupy after the rendered file set changes.
16. Gate in order with `make check-fmt`, `make lint`, `make typecheck`, and
   `make test`, logging each command through `tee`.

## Open decisions

| Decision | Default for implementation |
| --- | --- |
| Should generated projects default to `abi3` or `abi3t`? | No. Keep version-specific CPython wheels until a repository explicitly accepts stable-ABI restrictions. |
| Should the template always include `pyo3-build-config` and a build script? | No. Keep the minimal single-crate default and document the workspace/test-link escalation path. |
| Should wheel snapshots use syrupy? | Use plain pytest dictionaries in generated projects unless the template already renders syrupy into the project. Parent-template rendered-output checks should continue to use syrupy. |
| Should generated projects include `trybuild` by default? | No. Document it as an escalation path for bridge crates with real PyO3 signatures or macro patterns. |
| Should absent maturin fail or skip locally? | Skip the wheel build test when toolchain pieces are absent; fail pin parsing and static contract tests unconditionally. |

## References

- [Maturin user guide tutorial](https://www.maturin.rs/tutorial.html), accessed
  2026-06-14.
- [PyO3/maturin repository](https://github.com/PyO3/maturin), accessed
  2026-06-14.
- [PyO3 building and distribution guide](https://pyo3.rs/main/building-and-distribution),
  accessed 2026-06-14.
- [Python binary distribution format specification](https://packaging.python.org/specifications/binary-distribution-format/),
  accessed 2026-06-14.
- `leynos/prosidy-darn`, branch `test/maturin-pyo3-test-upgrade`, commit
  `65a9eee`.
- `leynos/cuprum`, `main`, commit `754d85a`.
- `leynos/tei-rapporteur`, `main`, commit `b9ba8c4`.
- `leynos/stilyagi`, `main`, commit `ea490e7`.
- `leynos/femtologging`, `main`, commit `691a739`.
