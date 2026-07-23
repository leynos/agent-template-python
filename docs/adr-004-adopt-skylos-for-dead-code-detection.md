# ADR-004: Adopt Skylos for dead-code detection

## Status

Proposed.

## Date

2026-07-24.

## Context and problem statement

Generated projects have strong formatting, linting, typechecking, testing, and
spelling gates, but none of those gates detects unused module-level functions,
classes, methods, or other code that remains syntactically valid. This gap is
particularly visible after large language model (LLM)-assisted changes: an LLM
can leave abandoned helpers, superseded implementations, or speculative code
behind while still satisfying the existing gates.

Python's dynamic features mean that dead-code detection is necessarily
conservative. Framework entry points, decorators, reflection, and string-based
dispatch can make live code appear unused. A template-wide gate therefore needs
both useful detection and disciplined, reviewable handling of false positives.
Suppressions must explain the hidden runtime edge; they must not become a
convenient way to preserve unexplained code.

## Decision drivers

- Detect dead Python code through the same public quality-gate interface as the
  existing linters.
- Prefer framework-aware analysis to reduce routine false positives.
- Keep the default check local and deterministic, without credentials, network
  access, or an LLM service.
- Make every accepted false positive narrow, justified, and visible in version
  control.
- Give contributors one documented path for adding an allowlist entry without
  encouraging bulk suppression.
- Keep local and Continuous Integration (CI) behaviour aligned through the
  existing `make lint` workflow.

## Options considered

### Skylos

[Skylos](https://github.com/duriantaco/skylos) provides a local static-analysis
command whose default scan includes dead-code detection. It understands common
Python framework conventions and supports project configuration, documented
symbol patterns, precise dead-code entry points, inline suppressions, runtime
tracing, and baselines. Its core analysis does not require its optional LLM
features or an application programming interface (API) key.

Skylos therefore supplies both the detector and the configuration surface
needed for projects that use dynamic dispatch. Its broader security, quality,
remediation, cloud, and LLM-assisted features are not part of this decision.

### deadcode

[deadcode](https://pypi.org/project/deadcode/) provides whole-project unused
code checks and `pyproject.toml` configuration. It remains classified as alpha,
however, and its most recent published release was in August 2024. That level
of maintenance activity is too weak for a new default dependency inherited by
every generated project.

### Vulture

[Vulture](https://github.com/jendrikseipp/vulture) is mature, fast, and
configurable, but evaluation in the template's target projects produced too
many false positives. Its own documentation notes the limits of static analysis
for implicitly called code and recommends maintaining a Python whitelist
module. Adopting it would make suppression maintenance too prominent a part of
the default contributor workflow.

### Rely on existing linters and review

Ruff and Pylint detect several unused local constructs, but they do not provide
the required whole-project reachability check. Human review is also an
unreliable sole control for plausible-looking, unused code introduced during
LLM-assisted work.

## Decision outcome and proposed direction

Adopt Skylos as the generated template's dead-code detector. Add it to the
generated development dependency group and run its local, static dead-code scan
from `lint-python`. Because `lint` already delegates to `lint-python`, and CI
already invokes `make lint`, this makes dead-code detection part of local and
hosted quality gates without a separate workflow.

Configure Skylos in the generated `pyproject.toml`. The initial policy should
scan the repository's tracked Python sources, use concise non-interactive
output, and fail the lint target when findings remain. Do not enable optional
LLM verification, automated remediation, security scanning, cloud upload, or
automatic code deletion as part of the lint gate.

Add a `make skylos-allow` target as the supported route for recording an
intentional false positive. The interface should require both a single symbol
or pattern and a reason, for example:

```bash
make skylos-allow NAME='registered_handler' \
  REASON='Loaded by the plugin registry through its entry-point name'
```

The target should delegate to Skylos' documented allowlist command, modify the
tracked `pyproject.toml`, and fail without both values. It must not scrape the
current report, generate a baseline, or accept multiple unexplained findings.

Allowlist entries follow these rules:

- Remove genuinely dead code instead of allowlisting it.
- Prefer a precise entry-point rule when a framework or parent type identifies
  the runtime edge more accurately than a name pattern.
- Otherwise, allowlist the narrowest stable symbol name; avoid wildcards unless
  a documented convention makes every match live.
- State who or what calls the symbol and how that runtime use was verified.
- Use a temporary entry with an owner, tracking reference, and expiry date when
  the evidence or need is temporary.
- Keep inline suppressions as a last resort for cases that cannot be expressed
  in project configuration, and include the reason beside the suppression.
- Remove stale entries in the same change that removes or replaces the dynamic
  use they describe.

## Goals and non-goals

- Goals:
  - Detect unused Python code in every generated project's standard lint gate.
  - Give contributors a repeatable, auditable false-positive workflow.
  - Make the policy discoverable to both coding agents and human contributors.
- Non-goals:
  - Automatically delete code reported by Skylos.
  - Treat static analysis alone as proof that code is safe to remove.
  - Adopt Skylos' security, cloud, LLM, or automated remediation features.
  - Add dead-code analysis for the optional Rust extension.

## Migration plan

1. Add Skylos to `template/pyproject.toml.jinja`, add its configuration, extend
   `lint-python` in `template/Makefile.jinja`, and implement the guarded
   `skylos-allow` target.
2. Extend the template contract tests to prove that rendered projects install
   Skylos, run it through `make lint`, reject undocumented allowlist additions,
   and expose the new target through `make help`.
3. Update `template/AGENTS.md.jinja` with the dead-code and allowlist policy, and
   update `template/docs/developers-guide.md` with the contributor workflow.
4. Add or update the parent repository's `docs/users-guide.md` to explain the
   dead-code gate and the generated `make skylos-allow` interface to template
   users.
5. Render representative Python-only and Rust-enabled projects, resolve genuine
   findings, justify any unavoidable exceptions, and run their full `make all`
   gates.

## Known risks and limitations

- Dynamic Python code can still produce false positives or false negatives;
  contributors must verify findings before removing code.
- A name-based allowlist can accidentally cover a later symbol with the same
  name. Narrow entry-point rules and routine review reduce, but do not eliminate,
  this risk.
- Skylos has a broader and faster-moving feature surface than this template
  needs. The generated configuration and documentation must keep the adopted
  surface limited to local dead-code detection.
- Adding another analyser increases environment size and lint time. The
  implementation should record representative timings and reconsider the gate
  if its cost materially disrupts the local workflow.

## Architectural rationale

In the context of generated Python projects that increasingly receive
LLM-assisted changes, facing plausible but unused code that passes the existing
quality gates, we decided for a local Skylos dead-code check with reasoned,
version-controlled exceptions, and against deadcode, Vulture, or review alone,
to achieve routine whole-project dead-code detection with manageable
false-positive handling, accepting another development dependency and the need
to maintain carefully scoped dynamic-code exceptions.

## Consequences

- Generated projects gain a blocking dead-code check under their existing
  `make lint` and `make all` interfaces.
- Contributors gain one guarded target for documented exceptions and assume
  responsibility for reviewing those exceptions as dynamic entry points change.
- The template repository must test and document the adopted Skylos command and
  configuration surface as Skylos evolves.
