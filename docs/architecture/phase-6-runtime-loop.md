# Phase 6 Runtime Loop

## Scope

Phase 6 implements the overall runtime execution loop only.

It turns the already-defined protocol layers into a deterministic top-level orchestration path. It does not redefine skeleton, scheduling, execution, acceptance, adoption, or migration truth.

Implemented scope:

- `RuntimeState` and terminal runtime status tracking
- top-level runtime entrypoints:
  - `run_experiment_runtime(...)`
  - `run_runtime(...)`
- overview validity integration before scheduler resolution
- module, phase, guide, and action resolution integration
- action execution / writeback entrypoint integration
- acceptance / promotion entrypoint integration
- overview revision + migration re-entry boundary
- terminal routing for:
  - `completed`
  - `paused`
  - `escalated`

Out of scope:

- scheduler redesign
- execution protocol redesign
- acceptance or adoption redesign
- migration redesign
- prompt generation
- persistence, API, UI, or product reporting
- generalized workflow/orchestration framework
- multi-agent workflows

## Integrated Layers

Phase 6 consumes the completed earlier layers as explicit entrypoints:

- overview validity checks over current runtime objects
- Phase 3 module resolution
- Phase 3 phase resolution
- Phase 3 guide resolution
- Phase 3 action resolution
- Phase 2 action execution / writeback helpers through a runtime entrypoint boundary
- Phase 4 phase, module, experiment, and adoption evaluation through acceptance entrypoints
- Phase 5 overview revision + migration outcomes:
  - `auto_resumed`
  - `pause_migration`
  - `escalate_migration`

The runtime loop coordinates those outputs. It does not silently reinterpret them.

## Runtime State

`RuntimeState` holds the current orchestration pointers:

- current overview version
- current module id
- current phase id
- current guide id
- current action id
- action records
- runtime status

It also keeps minimal orchestration context such as waiting context, issue evidence, and adopted results.

`ExperimentOverview` remains skeleton initialization structure, not runtime progress truth. `Module`, `Phase`, `ExecutionGuide`, `Action`, and `ActionRecord` preserve their earlier-phase ownership boundaries.

## Fixed Loop Order

The top-level runtime loop preserves this order:

1. terminal check
2. overview validity
3. module resolution
4. phase resolution
5. guide resolution
6. action resolution
7. execution / writeback
8. acceptance / promotion
9. terminal re-check

If a step pauses, escalates, revises, switches, or triggers migration, later stages in that iteration do not run.

## Migration Re-entry

Skeleton-level escalation enters the overview revision + migration subflow.

After `auto_resumed` migration, runtime state is rebound to the new version:

- overview, modules, and phases are replaced with new-version objects
- `current_overview_version` is updated
- `current_module_id` and `current_phase_id` come from the migration resume point
- `current_guide_id` is cleared
- `current_action_id` is cleared

This means old guide and action pointers are not silently reused across overview versions. A new valid guide/action must be resolved after migration re-entry.

If migration returns `pause_migration`, runtime status becomes `paused`. If migration returns `escalate_migration`, runtime status becomes `escalated`.

## Terminal States

Runtime terminal states are only:

- `completed`
- `paused`
- `escalated`

`completed` means experiment-level completion was reached through the acceptance path.

`paused` means the only legal continuation is waiting or manual intervention, including waiting-origin scheduler/action/acceptance routes or migration pause.

`escalated` means runtime cannot safely continue inside the current or migrated skeleton.

## Invariants

- old overview versions are not rewritten in place
- old active guide/action pointers are not reused after migration
- migration must derive a unique continuation module and phase
- guide lookup before action resolution must bind exactly one current guide
- adopted acceptance results are persisted into runtime state without changing adoption semantics
- no runtime branch silently guesses a module, phase, guide, or action

## Verification

Run the repository validation entrypoint:

```bash
scripts/check.sh
```

Run the full pytest suite directly:

```bash
pytest
```

Run Phase 6 runtime tests directly:

```bash
pytest tests/runtime/test_phase6_runtime.py
```
