# Phase 0 Baseline

## Current Scope

Phase 0 establishes the repository baseline for an experiment-oriented agent runtime. The emphasis is on structure and collaboration readiness rather than feature implementation.

## What Phase 0 Includes

- Minimal Python packaging configuration
- A typed package layout under `src/agent_runtime`
- Placeholder subpackages for future domains:
  - `models`
  - `execution`
  - `scheduling`
  - `acceptance`
  - `migration`
  - `common`
- Basic repository documentation
- A smoke test that verifies imports across the package surface
- A simple check script for running tests

## What Is Intentionally Not Implemented Yet

Phase 0 does not implement business logic beyond placeholders and importable package boundaries.

The following are intentionally deferred:

- Scheduler logic
- Migration logic
- Runtime execution logic
- Acceptance workflows beyond package placeholders
- UI or product-facing rendering
- Multi-agent workflows
- Broad architectural redesign or speculative abstraction layers

## Baseline Intent

The repository is prepared for later phases by reserving clear package boundaries for the major domains that are expected to evolve. Those boundaries are present now so later changes can remain incremental and explicit.
