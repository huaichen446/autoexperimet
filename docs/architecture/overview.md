# Architecture Overview

## Current Scope

The repository currently implements the baseline through Phase 3 for a skeleton-first experiment agent runtime.

Completed phases:

- Phase 0: repository and collaboration baseline
- Phase 1: object inventory and version boundaries
- Phase 2: `Action` / `ActionRecord` execution protocol
- Phase 3: runtime scheduling core

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

## Current Boundaries Between Layers

- skeleton objects define structure and version boundaries only
- runtime objects represent current mutable execution state
- `ExecutionGuide` controls the current round within one phase
- `ActionRecord` remains the source of truth for action execution state
- scheduler logic consumes runtime/execution state but does not rewrite protocol truth
- acceptance and migration boundaries remain separate and are not implemented here

## Pending Work For Later Phases

Phase 4 and Phase 5 are still pending. At repository level, the major unimplemented areas remain:

- acceptance / adoption engine
- migration engine
- non-linear phase topology
- persistence / database
- API layer
- UI / rendering
- multi-agent workflows

This overview intentionally stays aligned to what exists now. It does not define speculative future architecture beyond those still-pending boundaries.
