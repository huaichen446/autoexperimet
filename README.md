# Agent Runtime

Experiment-oriented, skeleton-first agent runtime in Python.

This repository defines typed protocol and runtime infrastructure for decomposing an experiment into overview, module, phase, guide, action, execution-record, acceptance, migration, and runtime-loop layers. It is an engineering baseline, not a product platform: there is no UI, API server, database layer, or multi-agent workflow framework here.

The codebase uses Python, Pydantic, and pytest.

## Current Status

Implemented through Phase 6:

- Phase 0: repository and collaboration baseline
- Phase 1: object inventory and version boundaries
- Phase 2: `Action` / `ActionRecord` execution protocol
- Phase 3: scheduling core
- Phase 4: acceptance and promotion mechanism
- Phase 5: skeleton rollback and version migration protocol
- Phase 6: overall runtime orchestration loop

The current default runtime model remains:

- single agent
- single experiment
- linear phase progression

## Implemented Phases

### Phase 0

Established the repository/package baseline, smoke-testable import surface, basic docs, and contributor check-script convention.

### Phase 1

Added Pydantic models for skeleton, runtime, execution-control, adoption, and inventory objects. `ObjectInventory` validates graph bindings and overview-version boundaries across the current object set.

### Phase 2

Implemented the `Action` / `ActionRecord` execution protocol. `ActionRecord` is the source of truth for single-attempt execution state, retry aggregation, finalized immutability, waiting resume, and late-arrival routing boundaries.

### Phase 3

Implemented deterministic scheduling for current module, phase, guide, and action resolution. Scheduler outcomes are explicit and include continue, retry, abandon-and-switch, waiting pause, revise-guide, and skeleton-escalation routes.

### Phase 4

Implemented structured acceptance and promotion helpers. `DecisionItem`, `DoneCheck`, and gate evaluators handle phase/module/experiment completion, while adoption validation promotes only evidence-backed accepted results.

### Phase 5

Implemented overview-version migration protocol. Migration freezes old active guides/attempts, handles structural mapping classes, preserves historical `ActionRecord` business truth, and resolves a unique resume module/phase or returns an explicit pause/escalate result.

### Phase 6

Implemented the top-level runtime orchestration loop. Runtime state coordinates overview validity, scheduler resolution, action execution/writeback entrypoint, acceptance/promotion entrypoint, and overview revision + migration re-entry without redesigning the lower layers.

## Repository Layout

- `src/agent_runtime/models`
  Pydantic models for skeleton objects, runtime objects, execution-control objects, adoption/archive objects, and aggregate inventory validation.

- `src/agent_runtime/execution`
  Phase 2 execution protocol helpers, validators, mirror sync, and late-arrival routing boundary.

- `src/agent_runtime/scheduling`
  Phase 3 scheduling core for module validation, phase validation, guide resolution, and action resolution.

- `src/agent_runtime/acceptance`
  Phase 4 acceptance and promotion helpers, including gate evaluators, routing helpers, and adopted-result validation.

- `src/agent_runtime/migration`
  Phase 5 migration helpers for overview-version transitions, mapping interpretation, freeze-before-mapping, resume routing, and historical-record relinking.

- `src/agent_runtime/runtime`
  Phase 6 runtime state, runtime results, orchestration handlers, overview validity helpers, and top-level runtime loop entrypoints.

- `docs/architecture`
  Architecture overview and phase-specific baseline documentation.

- `tests`
  Pytest coverage for models, execution protocol, scheduling, acceptance, migration, runtime orchestration, and smoke tests.

- `scripts`
  Repository validation script.

## Setup

Use Python 3.11 or newer.

Create and activate a virtual environment:

```bash
python -m venv .venv
```

On POSIX shells:

```bash
. .venv/bin/activate
```

On PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the project with development dependencies:

```bash
python -m pip install -e .[dev]
```

If you do not install the package editable, set `PYTHONPATH=src` before running tests.

PowerShell example:

```powershell
$env:PYTHONPATH="src"
python -m pytest
```

## Running Tests And Checks

Run the full test suite:

```bash
python -m pytest
```

Run the Phase 6 runtime tests:

```bash
python -m pytest tests/runtime/test_phase6_runtime.py
```

Run useful phase-specific slices:

```bash
python -m pytest tests/scheduling/test_phase3_scheduler.py
python -m pytest tests/acceptance/test_phase4_acceptance.py
python -m pytest tests/migration/test_phase5_migration.py
```

Run the repository validation script on a POSIX-compatible shell:

```bash
sh scripts/check.sh
```

The check script currently runs the full pytest suite and the Phase 6 runtime test slice with `PYTHONPATH=src`.

## Architecture Notes

The repository is organized as layered protocols and thin runtime orchestration:

- `ExperimentOverview` is skeleton initialization structure, not runtime progress truth.
- `Module` and `Phase` are runtime objects bound to one overview version.
- `ExecutionGuide` owns current-round execution control inside one phase.
- `Action` comes from the current valid guide.
- `ActionRecord` remains the execution truth source.
- scheduling resolves `module -> phase -> guide -> action` without silently guessing.
- acceptance evaluates explicit gates and promotion rules without rewriting scheduler or execution truth.
- migration handles overview-version transitions without rewriting historical execution business truth.
- runtime orchestration coordinates existing layers and clears stale guide/action pointers after migration re-entry.

For deeper design detail, start with [docs/architecture/overview.md](docs/architecture/overview.md) and [docs/architecture/phase-6-runtime-loop.md](docs/architecture/phase-6-runtime-loop.md).

## Non-Goals

The repository intentionally does not implement:

- UI / rendering
- persistence or database storage
- API layer
- multi-agent workflows
- product-facing reporting
- non-linear phase topology
- generalized workflow/orchestration framework
