# AGENTS.md

## Project
This repository implements an experiment-oriented agent runtime.

## Non-goals for Phase 0
- Do not redesign the overall architecture.
- Do not implement scheduler logic.
- Do not implement migration logic.
- Do not implement UI or product-facing rendering.
- Do not add multi-agent workflows.

## Required stack
- Python
- Pydantic
- pytest

## Phase 0 goal
Set up the repository and collaboration baseline only:
- project layout
- Python packaging baseline
- testing entrypoint
- docs folders
- repository instructions
- smoke tests

## Constraints
- Keep code minimal and typed.
- Prefer small, explicit files.
- Do not add speculative abstractions.
- Do not implement business logic beyond placeholders and smoke-level validation.
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
- src/agent_runtime/... package layout
- tests/test_smoke.py
- scripts/check.sh

## Definition of done
- `pytest -q` passes
- package imports succeed
- README explains setup and test commands
- architecture baseline doc exists