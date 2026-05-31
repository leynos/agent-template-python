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

## Consequences

`cuprum` makes allowed external programs explicit and keeps command execution
observable and testable. Scripts no longer rely on exception-driven handling of
non-zero command exits; they must check `CommandResult.exit_code` directly.

The template documentation now includes migration guidance for legacy
`plumbum` usage, but the preferred path for new and updated scripts is
`cuprum`.
