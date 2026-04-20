# Agent Runtime

Phase 1 model baseline for an experiment-oriented agent runtime repository.

The repository now includes typed Pydantic models for the object inventory, explicit overview-version boundaries, minimal architectural validators, and pytest coverage for the current schema baseline. The project is still intentionally narrow: Phase 1 defines model boundaries and validation only, not runtime business workflows.

## Current Status

Implemented in Phase 1:

- object inventory models across skeleton, runtime, execution-control, and archive/adoption layers
- explicit version boundaries between overview objects and runtime-bound objects
- minimal validators for required bindings, state-dependent required fields, and cross-object reference integrity
- model-focused tests covering construction, invalid state rejection, and version-boundary enforcement

Intentionally not implemented yet:

- scheduler logic
- execution engine logic
- acceptance engine logic
- migration engine logic
- UI or product-facing rendering

## Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install the project and test dependencies:

```bash
python -m pip install -e .[dev]
```

## Tests

Repository baseline check:

```bash
scripts/check.sh
```

Direct pytest invocation:

```bash
PYTHONPATH=src pytest -q
```

PowerShell equivalent:

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
│       └── phase-1-model-baseline.md
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
│       │   ├── adoption.py
│       │   ├── common.py
│       │   ├── execution.py
│       │   ├── inventory.py
│       │   ├── runtime.py
│       │   └── skeleton.py
│       └── scheduling/
└── tests/
    ├── test_models.py
    └── test_smoke.py
```

## Phase 1 Notes

- `src/agent_runtime/models/` is the current source of truth for the repository's schema baseline.
- `ObjectInventory` validates cross-layer references without introducing scheduler, execution, acceptance, or migration behavior.
- The baseline is deliberately conservative so later phases can build on stable model boundaries instead of reworking repository scaffolding.
