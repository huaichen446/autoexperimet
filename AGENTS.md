# AGENTS.md

## Repository Status
- Phase 0 completed
- Phase 1 completed
- Phase 2 completed

## Current Focus
- Phase 2 is complete and locked.
- Work in later phases may consume Phase 2 outputs but must not redesign the Phase 2 protocol truth model.

## Locked Phase 2 Protocol Rules
1. `Action` is a real executable runtime object.
2. `ActionRecord` is a single-attempt mutable record.
3. One action cannot have multiple active attempts at the same time.
4. Execution truth comes from `ActionRecord`, not from `Action` mirror fields.
5. `Action.status`, `Action.retry_count`, `Action.current_attempt_index`, `Action.last_failure_reason`, `Action.last_blocked_reason`, and `Action.last_record_id` are mirror-only cache fields.
6. `retry_count` truth comes from valid finalized `ActionRecord` aggregation.
7. Waiting resume continues the same attempt for `external_tool_not_ready`, `human_input_missing`, and `external_resource_not_ready`.
8. `selected -> abandoned` counts as a real attempt but not as a retry.
9. `skipped` belongs only to `Action` and does not create an `ActionRecord`.
10. Finalized `ActionRecord` business-state mutation is forbidden.
11. Late async results go to `LateArrivalRecord`, not back into the finalized `ActionRecord`.

## Later-Phase Boundary
- Later phases may schedule, consume, summarize, or react to Phase 2 protocol outputs.
- Later phases must not rewrite the attempt truth source.
- Later phases must not rewrite the retry truth source.
- Later phases must not rewrite waiting-resume ownership.
- Later phases must not rewrite finalized immutability.
- Later phases must not rewrite late-arrival routing.

## Still Out Of Scope Here
- Scheduler implementation
- Acceptance engine
- Adoption engine
- Migration engine
- UI / rendering
- Persistence layer
- API layer
- Multi-agent workflows
