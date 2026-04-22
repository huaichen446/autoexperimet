# Agent Runtime

Skeleton-first experiment agent runtime in Python.

## Purpose

This repository defines a layered runtime for experiment-oriented agent work. The implementation is intentionally incremental:

- skeleton objects define the stable experiment decomposition boundary
- runtime objects bind execution state back to the current overview version
- execution protocol objects define action-attempt truth through `ActionRecord`
- scheduling logic resolves the current module, phase, guide, and action without silently guessing

The codebase uses Python, Pydantic, and pytest only.

## Current Implementation Status

Implemented through Phase 3:

- Phase 0 baseline
- Phase 1 data models and version boundaries
- Phase 2 `Action` / `ActionRecord` execution protocol
- Phase 3 scheduling core

What is currently implemented:

- repository and packaging baseline
- typed Pydantic models across skeleton, runtime, execution-control, and inventory layers
- overview-version boundary validation through `ObjectInventory`
- Phase 2 action-attempt protocol helpers, mirror repair, and late-arrival routing boundary
- Phase 3 scheduling functions for module validation, phase validation, guide resolution, and action resolution
- explicit scheduler outcomes for continue, retry, abandon-and-switch, waiting pause, revise-guide, and escalate paths
- pytest coverage for models, execution protocol, and scheduler behavior

## What Is Not Implemented Yet

- acceptance / adoption engine
- migration engine
- non-linear phase topology
- UI / rendering
- persistence / database
- API layer
- multi-agent workflows

## Setup

Create and activate a Python 3.11+ virtual environment, then install the project with dev dependencies:

```bash
python -m pip install -e .[dev]
```

PowerShell note if you want to run tests without editable install:

```powershell
$env:PYTHONPATH="src"
pytest -q
```

## Tests

Run all tests:

```bash
pytest -q
```

Run the Phase 3 scheduler tests:

```bash
pytest tests/scheduling/test_phase3_scheduler.py -q
```

Optional repo smoke/check script:

```bash
scripts/check.sh
```

## Repository Layout

- `src/agent_runtime/models`
  Runtime, skeleton, execution-control, archive, and aggregate inventory models.
- `src/agent_runtime/execution`
  Phase 2 execution protocol helpers, validators, mirror sync, and late-arrival routing.
- `src/agent_runtime/scheduling`
  Phase 3 scheduling core for module, phase, guide, and action resolution.
- `src/agent_runtime/acceptance`
  Reserved package boundary for later acceptance/adoption work.
- `src/agent_runtime/migration`
  Reserved package boundary for later migration work.
- `docs`
  Architecture and phase baseline documentation.

## Current Boundaries

- `ExperimentOverview` is initialization skeleton, not runtime truth.
- `Module` and `Phase` are runtime objects bound to the current overview version.
- `ExecutionGuide` owns current-round execution control inside one phase.
- `Action` comes from the current valid guide.
- `ActionRecord` remains the execution truth source.
- scheduler resolution follows `module -> phase -> guide -> action`.
- acceptance, migration, persistence, API, UI, and non-linear topology are still out of scope.
