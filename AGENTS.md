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


## Phase 3 goal
Implement the runtime scheduling core only.

## In scope for Phase 3
- current module validation and selection
- current phase validation and selection
- current guide resolution
- current action resolution
- fixed result branching for:
  - continue_current_action
  - retry_current_action
  - abandon_current_action_and_switch
  - no_executable_action_pause
  - no_executable_action_revise_guide
  - no_executable_action_escalate
- waiting / revise / escalate routing
- minimal support code required to unblock scheduler tests if a small Phase 2 gap remains

## Out of scope for Phase 3
- full execution engine redesign
- acceptance engine
- adoption engine
- migration engine
- UI / rendering
- persistence/database
- API layer
- multi-agent workflows
- non-linear phase topology

## Hard constraints
1. Keep the three scheduling layers strictly separated:
   - module rules may not depend on action state
   - phase rules may not directly use action executability
   - action rules may not rewrite module/phase selection logic
2. Scheduler order must remain:
   - current module validation
   - current phase validation
   - current guide validation
   - current action resolution
3. Default model is:
   - single agent
   - single experiment
   - linear phase progression
4. If the current state cannot uniquely determine the next execution point, return an explicit scheduler result.
5. Do not silently guess a module, phase, or action.
6. Keep ActionRecord as the source of truth for action execution state.
7. Only fill Phase 2 gaps if they are the minimum required to make scheduler logic and tests executable.
8. Do not introduce acceptance or migration logic in this phase.

## Scheduler result vocabulary
Use explicit scheduler results only. Do not invent alternative wording.
At minimum support:
- continue_current_action
- retry_current_action
- abandon_current_action_and_switch
- pause_wait_external_tool_result
- pause_wait_human_input
- pause_wait_external_resource
- revise_guide_keep_phase
- escalate_to_overview_revision
- no_executable_action_pause
- no_executable_action_revise_guide
- no_executable_action_escalate

## Conflict priority
Use the fixed priority:
direct escalation > revise guide > pause waiting > keep current selection > switch selection

## Definition of done for Phase 3
- scheduler functions exist
- module/phase/guide/action resolution is testable
- explicit non-executable branches are returned instead of implicit fallthrough
- waiting / revise / escalate branches are covered by pytest
- no acceptance engine or migration engine is introduced