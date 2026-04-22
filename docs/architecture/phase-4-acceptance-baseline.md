# Phase 4 Acceptance Baseline

## Scope

Phase 4 implements the acceptance and promotion mechanism only.

Implemented scope:

- structured `DecisionItem` validation and closure handling
- structured `DoneCheck` validation and verifier-basis handling
- explicit phase, module, and experiment gate evaluators
- adoption / promotion checks for `AdoptedDesignItem`
- fixed acceptance failure routing
- pytest coverage for valid, invalid, blocked, revise, pause, escalate, and adoption paths

Out of scope:

- scheduler redesign
- execution protocol redesign
- migration logic
- persistence, API, or UI work
- document rendering or presentation systems
- orchestration framework or multi-agent workflows

## Core Roles

### `DecisionItem`

`DecisionItem` represents a required decision that must be explicitly closed for a scope.

In the current implementation it is used to model:

- phase-scoped required decisions
- module-scoped required decisions
- experiment-scoped required decisions

Acceptance does not treat `status == decided` as sufficient by itself. Required decisions are revalidated for:

- scope binding presence
- overview-version consistency
- complete closure fields such as selected option, evidence, and rationale

Malformed required decisions route to overview escalation rather than being silently accepted.

### `DoneCheck`

`DoneCheck` is the structured executable unit of done-criteria evaluation.

The current implementation supports:

- `record_based`
- `evidence_based`
- `threshold_based`
- `composite`

Required checks are revalidated at acceptance time for:

- scope binding
- overview-version consistency
- verifier type/config presence
- valid verifier basis for `met`
- stricter config requirements for threshold and composite checks

Invalid required checks escalate rather than falling through.

### `AdoptedDesignItem`

`AdoptedDesignItem` represents a promoted result that can survive beyond execution-layer outputs.

Promotion requires:

- a valid binding to closed acceptance truth
- a closed scope gate
- non-empty evidence
- non-empty content snapshot
- non-empty acceptance basis
- current overview-version compatibility
- source outputs that are not waiting-, blocked-, failed-, or temporary-only

Superseding an adopted result does not mutate the old result into a new meaning. The old item is marked `superseded`, and the new conclusion is represented by a separate adopted item.

## Gate Evaluators

The acceptance layer currently exposes:

- `evaluate_phase_gate(...)`
- `evaluate_module_gate(...)`
- `evaluate_experiment_gate(...)`

### Phase Gate

The phase gate checks:

- structural legality of the phase
- required phase decision closure
- required phase done-check closure
- blocked or invalid acceptance objects
- `state_after` satisfaction
- unresolved skeleton-level escalation conditions

### Module Gate

The module gate checks:

- module legality
- all module phases closed through phase-gate results
- required module decision closure
- required module done-check closure
- unresolved phase-level escalation

### Experiment Gate

The experiment gate checks:

- all modules closed through module-gate results
- required experiment decision closure
- required experiment done-check closure
- unresolved skeleton-level escalation
- overview-version consistency at experiment scope

## Acceptance Failure Routing

Acceptance failure uses explicit routing results only:

- `keep_current_state`
- `revise_guide`
- `pause_acceptance`
- `escalate_to_overview_revision`

The fixed priority is:

1. `escalate_to_overview_revision`
2. `pause_acceptance`
3. `revise_guide`
4. `keep_current_state`

This means:

- invalid or structurally inconsistent acceptance objects escalate immediately
- waiting-shaped blockers pause before any revise path
- revise applies only when the state is still repairable inside the current scope
- keep is used only when no higher-priority route applies

## Promotion Rules At A High Level

Promotion is intentionally stricter than execution success.

A candidate is promotable only when:

- its scope gate is already closed
- it binds to decided decisions or met required done checks in compatible scope lineage
- source records match the candidate scope and current overview version
- the result is not merely a note, temporary comparison, unresolved option, blocked output, or guide-revision support artifact

This keeps execution-layer observations separate from long-lived adopted design records.

## What Remains Out Of Scope

Phase 4 does not introduce:

- migration across overview versions
- scheduler-driven acceptance flow orchestration
- persistence or API behavior
- rendered product documentation systems
- non-linear topology handling
- multi-agent workflows
