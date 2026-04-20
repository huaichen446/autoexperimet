# Agent Runtime

Phase 0 baseline for an experiment-oriented agent runtime repository.

The goal of this phase is to establish a small, explicit collaboration and packaging foundation for later work. The repository intentionally includes only placeholder package structure, basic documentation, and smoke-level validation.

## Purpose

This project is intended to grow into an experiment-oriented agent runtime with clearly separated areas for models, execution, scheduling, acceptance, and migration. In Phase 0, those areas exist only as package boundaries so later phases can evolve without reworking repository setup.

## Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install the project and test dependencies:

```bash
python -m pip install -e .[dev]
```

## Tests

Use the repository-supported check command from the repository root:

```bash
scripts/check.sh
```

This is the canonical local Phase 0 check entrypoint. It runs the smoke test suite with the repository's expected import path configuration.

If you need to run the underlying command directly in PowerShell, use:

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
│       └── phase-0-baseline.md
├── pyproject.toml
├── pytest.ini
├── scripts/
│   └── check.sh
├── src/
│   └── agent_runtime/
│       ├── __init__.py
│       ├── acceptance/
│       ├── common/
│       ├── execution/
│       ├── migration/
│       ├── models/
│       └── scheduling/
└── tests/
    └── test_smoke.py
```

## Phase 0 Notes

- Includes package layout, packaging baseline, repository instructions, docs scaffolding, and smoke tests.
- Does not include scheduler behavior, migration behavior, runtime orchestration, or product-facing UI.
- Keeps implementation intentionally minimal to avoid speculative abstractions.
