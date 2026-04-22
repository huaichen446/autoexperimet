# Phase 5 Migration Baseline

## Scope

Phase 5 implements the skeleton-level rollback and version migration protocol only.

Implemented scope:

- overview-version migration objects and typed migration outcomes
- explicit old/new overview boundaries
- freeze-before-mapping behavior for active guides and active attempts
- module and phase mapping handling across the five structural mapping classes
- deterministic resume-point resolution for the default linear model
- explicit migration routing to:
  - `auto_resumed`
  - `pause_migration`
  - `escalate_migration`
- historical `ActionRecord` relinking with migration context annotations
- pytest coverage for auto-resume, pause, escalate, split ambiguity, reordered fallback, and historical-record immutability

Out of scope:

- scheduler redesign
- execution protocol redesign
- acceptance or adoption redesign
- persistence, API, or UI work
- workflow/orchestration framework
- non-linear phase topology

## Version Boundaries

Migration operates across two explicit skeleton versions:

- `old_overview`
- `new_overview`

The migration run records:

- `from_overview_version`
- `to_overview_version`
- typed mapping items for modules and phases
- the final migration decision and routing reason

Old and new overview objects are kept distinct. The old overview is superseded by the new version; the new overview records the old version as its parent boundary.

## Freeze Before Mapping

Phase 5 freezes active runtime execution objects before interpreting migration mappings.

This means:

- active old `ExecutionGuide` objects are superseded before resume planning
- active old `ActionRecord` attempts are frozen for migration before any new continuation is created
- migration must not carry forward live mutable execution objects without first freezing the old version boundary

This preserves the rule that old active guides do not remain active once migration starts.

## Structural Mapping Classes

The current implementation handles these mapping classes explicitly:

- `unchanged`
- `split`
- `merged`
- `removed`
- `reordered`

At a high level:

- `unchanged` preserves meaning only when the new phase still matches the old phase role and resulting state
- `split` may continue only when the continuation target is semantically unique
- `merged` evaluates source compatibility and may pause or escalate on conflict
- `removed` marks the old runtime object obsolete rather than silently inventing a continuation
- `reordered` preserves identity while allowing resume legality to move backward to an unfinished predecessor when required by the new order

The implementation stays deterministic and does not silently guess a resume path.

## Resume-Point Resolution

The default Phase 5 model remains:

- single agent
- single experiment
- linear phase progression

Resume-point resolution stays explicit and deterministic:

1. freeze old active runtime
2. validate mapping completeness
3. build migrated runtime objects from the new overview
4. apply phase migration rules
5. recompute module state from migrated phases
6. resolve a unique resume module
7. resolve a unique resume phase
8. create a fresh post-migration `ExecutionGuide`

If the next legal continuation point cannot be uniquely derived, migration returns an explicit pause or escalate result instead of guessing.

### Split Ambiguity

When an old done or in-progress phase/module is split into multiple new objects, Phase 5 only auto-resumes when exactly one split child is semantically justified as the continuation target.

If multiple split-derived candidates remain viable, migration pauses rather than using sort order as a proxy for meaning.

### Reordered Predecessor Fallback

When the old current phase still exists but the new order inserts unfinished predecessors before it, resume moves backward to the first unfinished predecessor.

If that predecessor fallback is not semantically unique, migration pauses instead of choosing by ordering alone.

## Failed-Phase Routing

Failed phase migration uses explicit three-way routing:

1. repaired in the new skeleton
   The mapped new phase resets to `not_started` and migration may continue.
2. repair status cannot be determined
   Migration returns `pause_migration`.
3. the failure remains structurally unresolved in the new skeleton
   Migration returns `escalate_migration`.

This logic is handled locally in migration rather than being hidden inside generic state recomputation.

## Historical `ActionRecord` Handling

Historical `ActionRecord` objects may be relinked and annotated for migration context, but their business truth is preserved.

The current migration layer may add:

- `frozen_by_migration_id`
- `migrated_to_overview_version`
- `migrated_resume_module_id`
- `migrated_resume_phase_id`
- revision / mutation metadata related to migration bookkeeping

The migration layer does not rewrite historical business-truth fields such as:

- `attempt_status`
- `failure_reason`
- `blocked_reason`
- `counts_as_retry`
- `finalized`

## Migration Outcomes

Phase 5 uses explicit migration outcomes only:

- `auto_resumed`
- `pause_migration`
- `escalate_migration`

Common pause conditions in the implemented baseline include:

- incomplete mapping
- split continuation ambiguity
- guide mapping not unique
- ambiguous resume module or phase
- indeterminate failed-phase repair status

Common escalate conditions in the implemented baseline include:

- active attempt conflict
- unresolved structural defects
- no legal continuation point

## What Phase 5 Added

With Phase 5 implemented, the repository now includes:

- a concrete migration package instead of a reserved boundary only
- deterministic migration planning across overview versions
- explicit freeze-before-mapping behavior
- typed handling of structural mapping classes
- resume-point derivation for the linear default model
- historical execution-record relinking without business-truth rewrite
