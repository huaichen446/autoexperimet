# AGENTS.md

## Project
This repository implements an experiment-oriented agent runtime.

## Non-goals for the current baseline
- Do not redesign the overall architecture.
- Do not implement scheduler logic.
- Do not implement migration logic.
- Do not implement execution engine logic.
- Do not implement acceptance engine logic.
- Do not implement UI or product-facing rendering.
- Do not add multi-agent workflows.

## Required stack
- Python
- Pydantic
- pytest

## Current baseline goal
Preserve and extend the Phase 1 model baseline only:
- object inventory models
- explicit version boundaries
- minimal architectural validators
- model and smoke tests
- repository instructions and baseline docs

## Constraints
- Keep code minimal and typed.
- Prefer small, explicit files.
- Do not add speculative abstractions.
- Do not implement business logic beyond schema-level validation.
- Keep skeleton, runtime, execution-control, and archive/adoption objects separate.
- Preserve explicit overview-version boundaries and binding references.
- Make the repository ready for later phases:
  - models
  - execution
  - scheduling
  - acceptance
  - migration

## Deliverables
- pyproject.toml
- pytest.ini
- README.md
- AGENTS.md
- docs/architecture/phase-0-baseline.md
- docs/architecture/phase-1-model-baseline.md
- src/agent_runtime/models/... schema layout
- src/agent_runtime/... package layout
- tests/test_models.py
- tests/test_smoke.py
- scripts/check.sh

## Definition of done
- `pytest -q` passes
- package imports succeed
- README explains setup, scope, and test commands
- architecture baseline docs exist
