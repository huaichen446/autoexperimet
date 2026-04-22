# Phase 3 Scheduling Baseline

## Scope

Phase 3 implements the runtime scheduling core only.

Implemented scope:

- current module validation and selection
- current phase validation and selection
- current guide resolution
- current action resolution
- explicit waiting / revise / escalate routing
- scheduler test coverage for deterministic outcomes

Out of scope:

- acceptance or adoption logic
- migration logic
- non-linear phase topology
- persistence, API, or UI work
- orchestration framework or multi-agent workflows

## Fixed Validation Order

The scheduler resolves the current execution point in this fixed order:

1. module
2. phase
3. guide
4. action

Earlier layers are always validated before later ones. The scheduler does not skip directly to action selection.

## Implemented Scheduler Outcomes

The current scheduling baseline returns explicit outcomes rather than implicit fallthrough.

Action-level outcomes implemented:

- `continue_current_action`
- `retry_current_action`
- `abandon_current_action_and_switch`
- `pause_wait_external_tool_result`
- `pause_wait_human_input`
- `pause_wait_external_resource`
- `revise_guide_keep_phase`
- `escalate_to_overview_revision`
- `no_executable_action_pause`
- `no_executable_action_revise_guide`
- `no_executable_action_escalate`

Supporting layer outcomes also exist for module and phase routing, including explicit module pause and module escalation paths.

## Guide Resolution Behavior

The current active guide must match:

- current module
- current phase
- current overview version
- `active` status

When multiple guides satisfy those constraints, the implemented tie-breaker is:

1. highest `guide_version`
2. latest `created_at`
3. smallest `guide_id`

If no valid guide exists, the scheduler returns local revise or overview escalation rather than guessing a guide.

## Action Resolution Behavior

Action resolution uses the current valid guide plus `ActionRecord`-derived truth.

Key behavior implemented:

- blocked classification is checked before continue or retry routing
- supported waiting reasons route to explicit waiting outcomes
- guide-repairable issues route to `revise_guide_keep_phase`
- structural boundary failures route to `escalate_to_overview_revision`
- retry is allowed only for retryable failures under retry limit
- `human_input` is not auto-retried
- abandoning the current action revalidates the same guide before reselection

### Action Tie-Breakers

When multiple legal actions exist in the same guide, selection uses:

1. actions supporting open `decision_items`
2. more supported open `decision_items`
3. actions supporting unmet done checks
4. `selected` or `running` over plain pending
5. higher `priority`
6. earlier `declared_order`
7. smaller `action_id`

If all legal actions support neither any open decision item nor any unmet done check, the scheduler does not pick one anyway. It escalates explicitly.

For `no_executable_action_pause`, the result is bound to one unique waiting `action_id` using:

1. higher `priority`
2. earlier `declared_order`
3. smaller `action_id`

## Waiting / Revise / Escalate Routing

Blocked action reasons currently route as follows:

- `external_tool_not_ready` -> wait for external tool result
- `human_input_missing` -> wait for human input
- `external_resource_not_ready` -> wait for external resource
- `guide_missing_info` -> revise guide within the current phase
- `undeclared_dependency` -> escalate to overview revision
- `fallback_boundary_violation` -> escalate to overview revision

The fixed priority applied during action resolution is:

- direct escalation
- revise guide
- pause waiting
- keep current selection
- switch selection

## Module And Phase Boundaries

Module selection is kept separate from action executability. It uses module legality, completion, dependency satisfaction, version validity, and blocked/failed state.

Blocked modules are not treated as automatic pause results. The current implementation pauses only for waiting-shaped blockage and escalates structural blockage when no legal alternative exists.

Phase selection is kept separate from action executability. It uses phase order, legality, version validity, completion, blocked/failed state, and `state_after` satisfaction.

## Known Non-Goals

This baseline intentionally does not implement:

- acceptance decisions
- adoption into long-lived design records
- migration across overview versions
- scheduler-driven persistence or API behavior
- non-linear module or phase graphs
- execution engine redesign

Phase 3 is a scheduling baseline only. It consumes the locked Phase 2 protocol but does not redefine it.
