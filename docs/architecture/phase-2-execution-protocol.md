# Phase 2 Execution Protocol

## Goal

Phase 2 implements the minimal executable protocol for `Action` / `ActionRecord` so one action lifecycle can be created, advanced, blocked, resumed, finalized, and validated in memory.

Phase 2 does not implement scheduler logic, acceptance/adoption, migration, UI, persistence, or API behavior.

## Scope

- `Action` / `ActionRecord` execution protocol only
- Protocol helpers and invariant validators
- Mirror repair from record truth
- Late-arrival routing boundary
- Protocol-focused tests

Out of scope:
- Scheduler
- Migration
- Acceptance / adoption engine
- UI / rendering
- Persistence layer
- API layer

## Locked Protocol Decisions

- `ActionRecord` is a single-attempt mutable record.
- One action may have at most one active attempt.
- Execution truth comes from `ActionRecord`.
- `Action` runtime fields are cache-only mirror fields.
- Retry truth comes from valid finalized `ActionRecord` aggregation.
- Waiting resume uses the same attempt.
- `selected -> abandoned` counts as an attempt but not a retry.
- `skipped` belongs only to `Action`.
- Finalized records reject business-state mutation.
- Late async results go to `LateArrivalRecord`.

## Core Protocol Boundaries

### Truth Source
- Current execution truth comes from the latest valid `ActionRecord` for an action.
- `Action.status`, `Action.retry_count`, `Action.current_attempt_index`, `Action.last_failure_reason`, `Action.last_blocked_reason`, and `Action.last_record_id` are mirrors only.

### Attempt States
- `ActionRecord.attempt_status` supports `selected`, `running`, `blocked`, `failed`, `done`, and `abandoned`.
- Active attempt states are `selected`, `running`, and `blocked`.
- `Action.status` may additionally represent `pending` and `skipped`.

### Required State-Dependent Fields
- `blocked` requires `blocked_reason`
- resumable blocked states require `waiting_target`
- `failed` requires `failure_reason`
- `done` requires `output_snapshot`
- finalized requires `finalized_at`

### Waiting / Resume Behavior
- Waiting resume continues the same attempt for:
  - `external_tool_not_ready`
  - `human_input_missing`
  - `external_resource_not_ready`
- Resumable blocked attempts must keep a `waiting_target`.
- Repeated human requests create a new attempt by default and do not count as retry by default.

### Retry Aggregation Rule
- Retry count is derived only from `ActionRecord` truth.
- Only valid or repaired finalized records with `counts_as_retry == true` contribute.
- `selected -> abandoned` is a real attempt but does not increment retry count.

### Finalization Boundary
- Only `done`, `failed`, and `abandoned` attempts may be finalized.
- Finalized business-state mutation is rejected.
- Late async results do not mutate finalized attempts and must be routed to `LateArrivalRecord`.

## Current Test Coverage

Current tests cover:
- Single active attempt invariant
- Latest valid record as execution truth
- Retry-count aggregation
- Waiting/resume on the same attempt
- `selected -> abandoned` behavior
- `skipped` behavior
- Mirror repair from record truth
- Finalized immutability
- Late-arrival routing

## Dependency Boundary To Later Phases

Later phases may consume this protocol for scheduling, acceptance, and migration work, but must not redefine:
- Attempt truth source
- Retry truth source
- Waiting resume ownership
- Finalized immutability
- Late-arrival routing
