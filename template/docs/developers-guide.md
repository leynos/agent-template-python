# Developer guide

This guide explains the contributor workflow for the generated project.

## Local workflow

Use `make all` as the public entrypoint for formatting, linting, typechecking,
and tests. Use narrower Make targets when investigating a specific failure, then
return to the aggregate gate before treating the change as complete.

## Automation scripts

Before adding or updating helper scripts, read
[Scripting standards](scripting-standards.md). New and updated scripts should
use `Cyclopts` for command-line interfaces, `cuprum` for typed and
catalogue-bound external command execution, `pathlib` for filesystem paths, and
`cmd-mox` when tests need to mock external executables.

Script changes should update the scripting guide when they introduce a new
convention, command catalogue, testing pattern, or operational expectation that
future contributors need to follow.
