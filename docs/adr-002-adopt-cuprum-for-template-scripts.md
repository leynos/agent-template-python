# ADR-002: Adopt cuprum for template script execution

## Status

Accepted.

## Context

The Python template documents helper-script conventions for generated projects.
Those scripts often need to invoke external command-line tools, and ad hoc
process execution makes command access, test doubles, error handling, and
observability harder to keep consistent.

The template now carries a scripting guide that standardizes on `Cyclopts` for
command-line interfaces, `pathlib` for filesystem paths, and `cmd-mox` for
command mocking. The command execution layer needs to match that model.

## Decision

Use `cuprum` as the documented command execution library for new and updated
Python helper scripts generated from this template.

Scripts should define or import an explicit `cuprum` command catalogue, create
commands within `sh.scoped(...)`, and inspect `CommandResult.exit_code`,
`stdout`, and `stderr` explicitly. Shared script suites may centralize common
catalogues in a project module, while standalone scripts and tests should keep
local catalogues scoped to the programs they need.

The generated documentation should signpost
`docs/scripting-standards.md` from contributor-facing instructions so script
authors find the `cuprum`, `Cyclopts`, `pathlib`, and `cmd-mox` conventions
before adding automation.

## Alternatives considered

### Continue using plumbum with local conventions

`plumbum` provides a simpler command API, but it does not make the allowed
command set a first-class part of the script contract. A script can still
construct new commands wherever `local[...]` is reachable, so command access
depends on reviewer discipline rather than an explicit catalogue. Lightweight
wrapper functions could reduce repetition, but they would recreate a partial
allowlist without enforcing scoped command construction across the script.

`plumbum` also makes observability a convention layered around command calls.
Common logging, tracing, and command auditing would need bespoke wrappers, and
those wrappers would be easy to bypass when a script author reaches directly for
`local[...]` or an imported command object. That is acceptable for small private
scripts, but it is a poor template default because generated projects inherit
the convention without the local context that produced it.

Finally, `plumbum` raises on non-zero exits by default. That can be convenient
for short scripts, but it encourages exception-driven control flow for command
results. The template's scripting guide instead expects command outcomes to be
observable values that tests can assert directly with `cmd-mox`.

### Use subprocess directly

The standard library `subprocess` module avoids a dependency, but it leaves
command allowlisting, argument construction, result handling, observability, and
test-double integration to each script. That would make the template guidance
longer and less consistent while still failing to provide a central enforcement
point for external program access.

## Consequences

`cuprum` introduces visible indirection through catalogues, scoped command
construction, and optional hooks. The template accepts that cost because it
makes allowed external programs explicit, gives generated projects a consistent
place to attach logging or auditing, and keeps command results testable as data.

Scripts no longer rely on exception-driven handling of non-zero command exits;
they must check `CommandResult.exit_code` directly. This is slightly more
verbose than `plumbum` for trivial calls, but it makes success and failure paths
clear in both production scripts and tests that mock external executables.

The template documentation now includes migration guidance for legacy
`plumbum` usage, but the preferred path for new and updated scripts is
`cuprum`.
