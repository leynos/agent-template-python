# ADR-005: Assert reusable-workflow shape, not pinned commit SHAs

## Status

Accepted.

## Context

Dependabot owns the upgrade of GitHub Actions and reusable workflows, including
calls into `leynos/shared-actions` from the generated mutation-testing
workflow. Contract tests that assert a caller's exact pinned commit SHA create
a lockstep dependency: every time Dependabot opens a bump PR, the test fails
until a human edits the pinned constant to match. That defeats the purpose of
automated dependency updates and turns a routine bump into a manual chore.

## Decision

Contract tests may verify the *shape* of a reusable-workflow caller. They must
not verify the specific SHA value.

- Do assert the workflow references the correct reusable workflow path.
- Do assert the ref is pinned to a full 40-character commit SHA, not a
  mutable branch such as `main` or `rolling`.
- Do assert the expected `on:` triggers, least-privilege `permissions:`,
  and the inputs the caller relies on.
- Do not hard-code the current SHA value as an expected string. Match it
  with a pattern instead.
- Do not fail a test purely because Dependabot bumped the pinned SHA.

If a workflow's behaviour genuinely depends on a feature only present from a
particular commit onwards, express that as a comment or a changelog note, not
as a test assertion on the SHA string.

## Consequences

- Dependabot bump PRs for reusable workflows pass the contract suite
  without manual intervention.
- Contract tests still catch structural regressions: a wrong workflow
  path, an unpinned or branch-pinned ref, or a dropped trigger, permission, or
  input.
- The suite cannot detect that a caller has drifted onto an unexpectedly
  old commit; that risk is accepted in exchange for automated upgrades.
