# Agent Runtime

Experiment-oriented agent runtime repository with typed models, explicit version boundaries, and a locked Phase 2 execution protocol for `Action` / `ActionRecord`.

## Current Phase Status
- Phase 0 completed
- Phase 1 completed
- Phase 2 completed

## Implemented So Far
- Repository baseline and package layout
- Typed Pydantic models
- Object inventory and overview-version boundaries
- `Action` runtime object modeling
- `ActionRecord` single-attempt execution protocol
- Protocol helpers for attempt creation, transitions, blocking, resume, completion, failure, abandonment, and finalization
- Mirror repair from `ActionRecord` truth
- Late-arrival routing to `LateArrivalRecord`
- Protocol-level pytest coverage

## Not Implemented Yet
- Scheduler
- Acceptance / adoption engine
- Migration engine
- UI / rendering
- Persistence / database
- API layer
- Multi-agent workflows

## Setup

Create and activate a Python 3.11+ virtual environment, then install the project with dev dependencies:

```bash
python -m pip install -e .[dev]
```

## Tests

Run the repository baseline check:

```bash
scripts/check.sh
```

Run the full test suite directly:

```bash
pytest -q
```

Run focused execution tests:

```bash
pytest -q tests/execution
```

PowerShell note if you want to call pytest directly without editable install:

```powershell
$env:PYTHONPATH="src"
pytest -q
```

## Repository Layout

```text
.
├── AGENTS.md
├── README.md
├── docs/
│   └── architecture/
│       ├── phase-0-baseline.md
│       ├── phase-1-model-baseline.md
│       └── phase-2-execution-protocol.md
├── pyproject.toml
├── pytest.ini
├── scripts/
│   └── check.sh
├── src/
│   └── agent_runtime/
│       ├── acceptance/
│       ├── common/
│       ├── execution/
│       ├── migration/
│       ├── models/
│       └── scheduling/
└── tests/
    ├── execution/
    ├── test_models.py
    └── test_smoke.py
```

## Current Boundaries

- `ActionRecord` is the execution truth source.
- `Action` runtime status fields are mirror-only cache fields.
- Retry truth comes from valid finalized `ActionRecord` aggregation.
- Waiting resume continues the same attempt for supported waiting states.
- Finalized business-state mutation is rejected.
- Scheduler, acceptance, migration, persistence, API, and UI remain outside the current repository scope.
