# Architecture Overview

## Current Scope

The repository currently implements the baseline through Phase 6 for a skeleton-first experiment agent runtime.

Completed phases:

- Phase 0: repository and collaboration baseline
- Phase 1: object inventory and version boundaries
- Phase 2: `Action` / `ActionRecord` execution protocol
- Phase 3: runtime scheduling core
- Phase 4: acceptance and promotion layer
- Phase 5: overview-version migration and resume routing
- Phase 6: top-level runtime loop orchestration

The current default model is:

- single agent
- single experiment
- linear phase progression

## Architecture Layers

### Skeleton Layer

The skeleton layer defines the stable decomposition boundary for an experiment:

- `ExperimentOverview`
- `ModuleOverview`
- `PhaseOverview`

This layer is initialization structure only. It does not hold runtime truth for execution progress.

### Runtime Layer

The runtime layer materializes current objects against one overview version:

- `Module`
- `Phase`
- `ActionRecord`

Runtime objects bind back to skeleton references instead of mutating the overview.

### Execution-Control Layer

The execution-control layer defines current-round planning and action candidates:

- `ExecutionGuide`
- `DecisionItem`
- `DoneCheck`
- `Action`

`ExecutionGuide` owns the current execution round inside one phase. `Action` belongs to a guide, but action execution truth still comes from `ActionRecord`.

### Scheduling Layer

The scheduling layer resolves the current execution point in a fixed order:

1. current module validation
2. current phase validation
3. current guide validation
4. current action resolution

It does not redesign execution truth, acceptance, or migration behavior. It returns explicit outcomes when the runtime state cannot continue directly.

### Acceptance Layer

The acceptance layer evaluates deterministic completion and promotion state without redefining scheduler or execution truth.

Implemented Phase 4 objects and helpers:

- `DecisionItem`
- `DoneCheck`
- `AdoptedDesignItem`
- `evaluate_phase_gate(...)`
- `evaluate_module_gate(...)`
- `evaluate_experiment_gate(...)`
- `evaluate_adoption_candidate(...)`

At a high level:

- `DecisionItem` represents a required decision that must close explicitly for a scope
- `DoneCheck` is the executable unit of done-criteria evaluation
- `AdoptedDesignItem` is a promoted result that is allowed to survive beyond execution-layer outputs
- gate evaluation stays separate from scheduler selection logic
- promotion requires closed gates, valid bindings, evidence, acceptance basis, and non-temporary source outputs

### Migration Layer

The migration layer handles deterministic overview-version transitions without redesigning execution, scheduling, or acceptance truth.

Implemented Phase 5 objects and helpers:

- `OverviewMigration`
- `ModuleMigrationItem`
- `PhaseMigrationItem`
- `migrate_overview(...)`
- freeze and relink helpers for guides and historical action records

At a high level:

- migration works across explicit old/new overview boundaries
- active guides and active attempts are frozen before mapping is interpreted
- structural changes are handled through explicit mapping classes
- resume-point resolution must derive a unique module and phase or return a typed pause/escalate outcome
- historical `ActionRecord` business truth remains immutable during relinking

### Runtime Loop Layer

The runtime loop layer orchestrates the completed lower-level protocols without redesigning them.

Implemented Phase 6 objects and helpers:

- `RuntimeState`
- `run_experiment_runtime(...)`
- `run_runtime(...)`
- explicit orchestration handlers for module, phase, guide, action, execution, acceptance, and migration outcomes

The loop order is fixed:

1. terminal check
2. overview validity
3. module resolution
4. phase resolution
5. guide resolution
6. action resolution
7. execution / writeback
8. acceptance / promotion
9. terminal re-check

Skeleton-level escalation enters the overview revision + migration boundary. After successful migration, the runtime re-derives continuation pointers from the new overview version and clears stale guide/action pointers.

## What Each Completed Phase Delivered

### Phase 0

- repository/package baseline
- reserved package boundaries
- smoke-testable import surface
- basic collaboration and check-script setup

### Phase 1

- Pydantic model baseline
- aggregate inventory validation in `ObjectInventory`
- overview-version boundary enforcement across skeleton, runtime, guide, and action-record layers

### Phase 2

- executable `Action` / `ActionRecord` protocol helpers
- single-active-attempt enforcement
- finalized immutability boundary
- retry aggregation from finalized valid records
- waiting-resume ownership on the same attempt for supported waiting states
- late-arrival routing boundary

### Phase 3

- module validation and selection
- phase validation and selection inside the current module
- active guide resolution with fixed tie-breakers
- current action resolution with explicit waiting, revise, escalate, continue, retry, and abandon-and-switch outcomes
- scheduler tests for explicit no-fallthrough behavior

### Phase 4

- acceptance models for structured decision closure and done-check evaluation
- explicit phase, module, and experiment gate evaluators
- fixed acceptance routing outcomes:
  - `keep_current_state`
  - `revise_guide`
  - `pause_acceptance`
  - `escalate_to_overview_revision`
- adopted-result promotion checks for scope closure, evidence, acceptance basis, and source compatibility
- supersede behavior that preserves prior adopted items instead of silently rewriting them

### Phase 5

- migration objects for old/new overview transitions
- freeze-before-mapping behavior for active guides and active attempts
- explicit handling of `unchanged`, `split`, `merged`, `removed`, and `reordered` mapping classes
- deterministic resume module / resume phase resolution for the default linear model
- explicit migration outcomes for auto-resume, pause, and escalate paths
- historical `ActionRecord` relinking that adds migration context without rewriting business-truth fields

### Phase 6

- runtime state object for current overview/module/phase/guide/action pointers
- top-level runtime entrypoints
- fixed orchestration order across overview validity, scheduling, execution, acceptance, and migration
- explicit terminal routing for `completed`, `paused`, and `escalated`
- migration re-entry behavior that replaces current-version runtime objects and clears guide/action pointers
- pytest coverage for loop order, pause/escalation/completion, migration re-entry, guide binding safety, and adopted-result persistence

## Current Boundaries Between Layers

- skeleton objects define structure and version boundaries only
- runtime objects represent current mutable execution state
- `ExecutionGuide` controls the current round within one phase
- `ActionRecord` remains the source of truth for action execution state
- scheduler logic consumes runtime/execution state but does not rewrite protocol truth
- acceptance consumes runtime/execution outputs but does not rewrite scheduler or execution truth
- migration consumes runtime history and overview mappings without rewriting execution business truth
- runtime orchestration coordinates the existing layers without redesigning their internals

## Pending Work For Later Phases

Later phases are still pending. At repository level, the major unimplemented areas remain:

- non-linear phase topology
- persistence / database
- API layer
- UI / rendering
- multi-agent workflows

This overview intentionally stays aligned to what exists now. It does not define speculative future architecture beyond those still-pending boundaries.
