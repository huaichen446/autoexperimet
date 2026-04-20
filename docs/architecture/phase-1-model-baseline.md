# Phase 1 Model Baseline

## Scope

Phase 1 establishes the repository's object-model baseline only. The intent is to define the inventory of core objects, preserve version boundaries between skeleton and runtime layers, and enforce only minimal architectural invariants through Pydantic validation.

This phase does not implement workflow behavior. It does not schedule work, execute actions, accept outcomes, migrate data, or render UI.

## Object Layers

The current model package is organized into four object layers plus one aggregate validation view:

- Skeleton layer:
  - `ExperimentOverview`
  - `ModuleOverview`
  - `PhaseOverview`
- Runtime layer:
  - `Module`
  - `Phase`
  - `ActionRecord`
- Execution-control layer:
  - `ExecutionGuide`
  - `DecisionItem`
  - `DoneCheck`
  - `Action`
- Archive/adoption layer:
  - `ExperimentMainDoc`
  - `AdoptedDesignItem`
- Aggregate inventory validation:
  - `ObjectInventory`

The skeleton layer remains distinct from runtime objects. Runtime objects bind back to overview objects through explicit reference fields rather than embedding or mutating the skeleton definitions.

## Version Boundary Rules

Phase 1 preserves version boundaries explicitly.

- `ExperimentOverview.version` is the baseline overview version for a model inventory snapshot.
- `ModuleOverview.overview_version` and `PhaseOverview.overview_version` must match the parent experiment overview version.
- Runtime objects carry `overview_version` and bind back to skeleton objects through:
  - `Module.module_overview_ref`
  - `Phase.phase_overview_ref`
- `Module.overview_version`, `Phase.overview_version`, `ExecutionGuide.overview_version`, and `ActionRecord.overview_version` must match the active experiment overview version in the validated inventory.
- Archive items preserve the same version boundary through `AdoptedDesignItem.source_overview_version`.

These rules are validated structurally. Phase 1 does not define migration or reconciliation behavior across versions.

## Validator Coverage

Validators in this phase are intentionally narrow and architecture-facing.

- Local model validation ensures required binding identifiers are present.
- State-dependent validation enforces minimal required fields for blocked, failed, decided, met, or terminal record states.
- Relationship validation ensures:
  - `ExperimentOverview` owns one or more `ModuleOverview` objects.
  - `ModuleOverview` owns one or more `PhaseOverview` objects.
  - runtime modules and phases bind to existing overview references.
  - execution guides bind to existing runtime module and phase objects.
  - actions are guide-scoped and action records point to an existing guide-owned action.
  - archive items reference existing runtime and guide objects when present.
- Aggregate inventory validation is centralized in `ObjectInventory` so cross-object constraints remain separate from future workflow engines.

No validator in this phase implements orchestration policy, retries, scheduling semantics, acceptance rules, or migration logic.

## What Remains for Phase 2+

Later phases can build behavior on top of the current model boundaries, including:

- scheduler and phase/module progression rules
- execution engine behavior for guides and actions
- acceptance and adoption decision logic
- migration/version-transition logic
- richer persistence and UI-facing representations

Those later phases should preserve the current layer separation and explicit reference boundaries unless a future architecture change is intentionally approved.
