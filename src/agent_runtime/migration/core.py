"""Phase 5 migration planning, freezing, mapping, and resume helpers."""

from __future__ import annotations

from collections import defaultdict

from agent_runtime.models import (
    ActionRecord,
    ActionRecordStatus,
    ExecutionGuide,
    ExperimentOverview,
    GuideStatus,
    Module,
    ModuleStatus,
    Phase,
    PhaseStatus,
)

from .models import (
    MigrationDecision,
    MigrationItemResult,
    MigrationMappingType,
    MigrationOutcomeKind,
    MigrationRunResult,
    MigrationStatus,
    ModuleMigrationItem,
    OverviewMigration,
    PhaseMigrationItem,
    StateInheritanceMode,
)


WAITING_BLOCKERS = {
    "external_tool_not_ready",
    "human_input_missing",
    "external_resource_not_ready",
}

FAILED_PHASE_REPAIR_CONFIRMED = {
    "repaired",
    "repaired_root_cause",
}

FAILED_PHASE_REPAIR_UNKNOWN = {
    "repair_status_unknown",
    "indeterminate_repair",
}

FAILED_PHASE_STILL_BROKEN = {
    "still_broken",
    "structural_defect_unresolved",
}


def has_complete_mapping(
    old_overview: ExperimentOverview,
    new_overview: ExperimentOverview,
    module_mapping: list[ModuleMigrationItem],
    phase_mapping: list[PhaseMigrationItem],
) -> bool:
    """Return True only when every old and new skeleton object is covered by migration items."""

    old_module_ids = {module.module_overview_id for module in old_overview.modules}
    new_module_ids = {module.module_overview_id for module in new_overview.modules}
    mapped_old_module_ids = {item.old_module_id for item in module_mapping if item.old_module_id is not None}
    mapped_new_module_ids = {item.new_module_id for item in module_mapping if item.new_module_id is not None}

    old_phase_ids = {
        phase.phase_overview_id
        for module in old_overview.modules
        for phase in module.phase_overviews
    }
    new_phase_ids = {
        phase.phase_overview_id
        for module in new_overview.modules
        for phase in module.phase_overviews
    }
    mapped_old_phase_ids = {item.old_phase_id for item in phase_mapping if item.old_phase_id is not None}
    mapped_new_phase_ids = {item.new_phase_id for item in phase_mapping if item.new_phase_id is not None}

    return (
        old_module_ids == mapped_old_module_ids
        and new_module_ids == mapped_new_module_ids
        and old_phase_ids == mapped_old_phase_ids
        and new_phase_ids == mapped_new_phase_ids
    )


def has_active_attempt_conflict(action_records: list[ActionRecord]) -> bool:
    """Detect conflicting active old attempts that make migration unsafe."""

    active_by_action: dict[str, int] = defaultdict(int)
    for record in action_records:
        if record.attempt_status in {
            ActionRecordStatus.SELECTED,
            ActionRecordStatus.RUNNING,
            ActionRecordStatus.BLOCKED,
        }:
            active_by_action[record.action_id] += 1
    return any(count > 1 for count in active_by_action.values())


def has_unresolved_structural_violation(
    new_overview: ExperimentOverview,
    old_phases: list[Phase],
) -> str | None:
    """Return an escalate reason code when the new skeleton is still structurally unsafe."""

    new_module_names = {module.name for module in new_overview.modules}
    for module in new_overview.modules:
        missing_dependencies = [name for name in module.depends_on_module_names if name not in new_module_names]
        if missing_dependencies:
            return "undeclared_dependency_still_present"
    return None


def _split_continuation_candidates(items: list[ModuleMigrationItem] | list[PhaseMigrationItem]) -> list[str]:
    """Return only explicitly justified split continuation targets."""

    explicit_unique = [item for item in items if item.reason_code == "unique_coverage"]
    if explicit_unique:
        return [
            target_id
            for item in explicit_unique
            if (target_id := getattr(item, "new_phase_id", None) or getattr(item, "new_module_id", None)) is not None
        ]

    partial_targets = [
        target_id
        for item in items
        if item.state_inheritance_mode == StateInheritanceMode.PARTIAL
        and (target_id := getattr(item, "new_phase_id", None) or getattr(item, "new_module_id", None)) is not None
    ]
    if len(partial_targets) == 1:
        return partial_targets
    return []


def detect_split_resume_ambiguity(
    old_modules: list[Module],
    old_phases: list[Phase],
    module_mapping: list[ModuleMigrationItem],
    phase_mapping: list[PhaseMigrationItem],
) -> tuple[MigrationOutcomeKind, str] | None:
    """Pause when split mappings do not expose exactly one semantic continuation target."""

    module_items_by_old: dict[str, list[ModuleMigrationItem]] = defaultdict(list)
    for item in module_mapping:
        if item.old_module_id is not None:
            module_items_by_old[item.old_module_id].append(item)

    for old_module in old_modules:
        items = module_items_by_old.get(old_module.module_id, [])
        if not items or items[0].mapping_type != MigrationMappingType.SPLIT:
            continue
        if old_module.status not in {ModuleStatus.DONE, ModuleStatus.IN_PROGRESS}:
            continue
        target_ids = [item.new_module_id for item in items if item.new_module_id is not None]
        if len(target_ids) <= 1:
            continue
        if len(_split_continuation_candidates(items)) != 1:
            return MigrationOutcomeKind.PAUSE_MIGRATION, "split_module_coverage_ambiguous"

    phase_items_by_old: dict[str, list[PhaseMigrationItem]] = defaultdict(list)
    for item in phase_mapping:
        if item.old_phase_id is not None:
            phase_items_by_old[item.old_phase_id].append(item)

    for old_phase in old_phases:
        items = phase_items_by_old.get(old_phase.phase_id, [])
        if not items or items[0].mapping_type != MigrationMappingType.SPLIT:
            continue
        if old_phase.status not in {PhaseStatus.DONE, PhaseStatus.IN_PROGRESS}:
            continue
        target_ids = [item.new_phase_id for item in items if item.new_phase_id is not None]
        if len(target_ids) <= 1:
            continue
        if len(_split_continuation_candidates(items)) != 1:
            return MigrationOutcomeKind.PAUSE_MIGRATION, "split_phase_coverage_ambiguous"

    return None


def freeze_all_old_active_guides(
    guides: list[ExecutionGuide],
    *,
    migration_id: str,
) -> list[ExecutionGuide]:
    """Supersede all old guides so none remain active after migration starts."""

    frozen_guides: list[ExecutionGuide] = []
    for guide in guides:
        frozen_actions = []
        for action in guide.actions:
            frozen_actions.append(
                action.model_copy(
                    update={
                        "status": None,
                        "current_attempt_index": None,
                        "retry_count": None,
                        "last_failure_reason": None,
                        "last_blocked_reason": None,
                        "last_record_id": None,
                    }
                )
            )
        frozen_guides.append(
            guide.model_copy(
                update={
                    "status": GuideStatus.SUPERSEDED,
                    "superseded_by": migration_id,
                    "actions": frozen_actions,
                }
            )
        )
    return frozen_guides


def freeze_all_old_active_attempts(
    action_records: list[ActionRecord],
    *,
    migration_id: str,
    to_overview_version: int,
) -> list[ActionRecord]:
    """Freeze active old attempts so later execution helpers reject business-state writes."""

    frozen_records: list[ActionRecord] = []
    for record in action_records:
        if record.attempt_status in {
            ActionRecordStatus.SELECTED,
            ActionRecordStatus.RUNNING,
            ActionRecordStatus.BLOCKED,
        }:
            frozen_records.append(
                record.model_copy(
                    update={
                        "frozen_by_migration_id": migration_id,
                        "migrated_to_overview_version": to_overview_version,
                        "record_revision": record.record_revision + 1,
                        "mutation_reason_code": "migration_frozen",
                    }
                )
            )
        else:
            frozen_records.append(record.model_copy())
    return frozen_records


def freeze_old_active_runtime(
    guides: list[ExecutionGuide],
    action_records: list[ActionRecord],
    *,
    migration_id: str,
    to_overview_version: int,
) -> tuple[list[ExecutionGuide], list[ActionRecord]]:
    """Freeze all active old guide and attempt objects before any mapping proceeds."""

    return (
        freeze_all_old_active_guides(guides, migration_id=migration_id),
        freeze_all_old_active_attempts(
            action_records,
            migration_id=migration_id,
            to_overview_version=to_overview_version,
        ),
    )


def mark_old_objects_superseded_or_obsolete(
    old_modules: list[Module],
    old_phases: list[Phase],
    module_mapping: list[ModuleMigrationItem],
    phase_mapping: list[PhaseMigrationItem],
) -> tuple[list[Module], list[Phase]]:
    """Mark removed old runtime objects obsolete while preserving historical copies."""

    removed_module_ids = {
        item.old_module_id
        for item in module_mapping
        if item.mapping_type == MigrationMappingType.REMOVED and item.old_module_id is not None
    }
    removed_phase_ids = {
        item.old_phase_id
        for item in phase_mapping
        if item.mapping_type == MigrationMappingType.REMOVED and item.old_phase_id is not None
    }

    frozen_modules = [
        module.model_copy(update={"status": ModuleStatus.OBSOLETE})
        if module.module_id in removed_module_ids
        else module.model_copy()
        for module in old_modules
    ]
    frozen_phases = [
        phase.model_copy(update={"status": PhaseStatus.OBSOLETE})
        if phase.phase_id in removed_phase_ids
        else phase.model_copy()
        for phase in old_phases
    ]
    return frozen_modules, frozen_phases


def inherit_allowed_runtime_context(old_module: Module | None) -> dict:
    """Copy only minimal historical context that remains safe after migration."""

    if old_module is None:
        return {"notes": [], "failure_reasons": [], "retry_history": []}
    return {
        "notes": list(old_module.notes),
        "failure_reasons": list(old_module.failure_reasons),
        "retry_history": list(old_module.retry_history),
    }


def relink_historical_action_records(
    action_records: list[ActionRecord],
    *,
    migration_id: str,
    resume_module_id: str | None,
    resume_phase_id: str | None,
    to_overview_version: int,
) -> list[ActionRecord]:
    """Annotate historical records with migration context without rewriting business truth."""

    return [
        record.model_copy(
            update={
                "frozen_by_migration_id": record.frozen_by_migration_id or migration_id,
                "migrated_to_overview_version": to_overview_version,
                "migrated_resume_module_id": resume_module_id,
                "migrated_resume_phase_id": resume_phase_id,
                "record_revision": record.record_revision + 1,
                "mutation_reason_code": "migration_relinked",
            }
        )
        for record in action_records
    ]


def build_modules_from_overview(
    overview: ExperimentOverview,
    module_mapping: list[ModuleMigrationItem],
    old_modules: list[Module],
) -> list[Module]:
    """Create new runtime modules from the new overview and limited inherited context."""

    old_modules_by_id = {module.module_id: module for module in old_modules}
    modules: list[Module] = []

    for module_overview in sorted(overview.modules, key=lambda item: (item.sort_index, item.module_overview_id)):
        mapping_item = next((item for item in module_mapping if item.new_module_id == module_overview.module_overview_id), None)
        old_module = old_modules_by_id.get(mapping_item.old_module_id) if mapping_item and mapping_item.old_module_id else None
        inherited = inherit_allowed_runtime_context(old_module if mapping_item and mapping_item.state_inheritance_mode != StateInheritanceMode.NONE else None)
        modules.append(
            Module(
                module_id=module_overview.module_overview_id,
                experiment_id=overview.experiment_id,
                overview_version=overview.version,
                module_overview_ref=module_overview.module_overview_id,
                name=module_overview.name,
                goal=module_overview.goal,
                phase_ids=[phase.phase_overview_id for phase in sorted(module_overview.phase_overviews, key=lambda item: (item.sort_index, item.phase_overview_id))],
                current_phase_id=None,
                completed_phase_ids=[],
                blocked_phase_ids=[],
                status=ModuleStatus.NOT_STARTED,
                notes=inherited["notes"],
                failure_reasons=inherited["failure_reasons"],
                retry_history=inherited["retry_history"],
                needs_redecomposition=False,
                created_at=overview.created_at,
                updated_at=overview.created_at,
            )
        )
    return modules


def build_phases_from_overview(overview: ExperimentOverview) -> list[Phase]:
    """Create new runtime phases bound to the new overview version."""

    phases: list[Phase] = []
    for module_overview in sorted(overview.modules, key=lambda item: (item.sort_index, item.module_overview_id)):
        for phase_overview in sorted(module_overview.phase_overviews, key=lambda item: (item.sort_index, item.phase_overview_id)):
            phases.append(
                Phase(
                    phase_id=phase_overview.phase_overview_id,
                    module_id=module_overview.module_overview_id,
                    experiment_id=overview.experiment_id,
                    overview_version=overview.version,
                    phase_overview_ref=phase_overview.phase_overview_id,
                    name=phase_overview.name,
                    role=phase_overview.role,
                    state_after=phase_overview.state_after,
                    status=PhaseStatus.NOT_STARTED,
                    is_expanded=False,
                    notes=[],
                    failure_reasons=[],
                    retry_history=[],
                    fallback_boundary=phase_overview.transition_to_next,
                    created_at=overview.created_at,
                    updated_at=overview.created_at,
                )
            )
    return phases


def _preserves_phase_meaning(old_phase: Phase, new_phase: Phase) -> bool:
    return old_phase.role == new_phase.role and old_phase.state_after == new_phase.state_after


def classify_failed_phase_migration(
    old_phase: Phase,
    items: list[PhaseMigrationItem],
) -> tuple[str, str | None]:
    """Classify failed-phase migration into repaired, indeterminate, or still broken."""

    if old_phase.status != PhaseStatus.FAILED:
        return "not_failed", None

    reason_codes = {item.reason_code for item in items if item.reason_code}
    if reason_codes & FAILED_PHASE_REPAIR_CONFIRMED:
        return "repaired", None
    if reason_codes & FAILED_PHASE_STILL_BROKEN:
        if "fallback_boundary_violation" in old_phase.failure_reasons:
            return "still_broken", "fallback_boundary_violation_still_present"
        if "undeclared_dependency" in old_phase.failure_reasons:
            return "still_broken", "undeclared_dependency_still_present"
        return "still_broken", "failed_phase_still_structurally_broken"
    if reason_codes & FAILED_PHASE_REPAIR_UNKNOWN or not reason_codes:
        return "indeterminate", "failed_phase_repair_indeterminate"
    return "indeterminate", "failed_phase_repair_indeterminate"


def handle_module_mapping(
    old_modules: list[Module],
    module_mapping: list[ModuleMigrationItem],
) -> dict[str, ModuleMigrationItem]:
    """Return module mapping lookup keyed by new module id."""

    del old_modules
    return {
        item.new_module_id: item
        for item in module_mapping
        if item.new_module_id is not None
    }


def handle_phase_mapping(
    old_phases: list[Phase],
    new_phases: list[Phase],
    phase_mapping: list[PhaseMigrationItem],
) -> tuple[list[Phase], MigrationOutcomeKind | None, str | None]:
    """Apply phase migration rules and return updated new phases plus pause/escalate signals."""

    old_by_id = {phase.phase_id: phase for phase in old_phases}
    new_by_id = {phase.phase_id: phase for phase in new_phases}
    items_by_old: dict[str, list[PhaseMigrationItem]] = defaultdict(list)
    items_by_new: dict[str, list[PhaseMigrationItem]] = defaultdict(list)
    for item in phase_mapping:
        if item.old_phase_id is not None:
            items_by_old[item.old_phase_id].append(item)
        if item.new_phase_id is not None:
            items_by_new[item.new_phase_id].append(item)

    updated = {phase.phase_id: phase.model_copy() for phase in new_phases}

    for old_phase_id, items in items_by_old.items():
        old_phase = old_by_id.get(old_phase_id)
        if old_phase is None:
            continue

        first_item = items[0]
        mapping_type = first_item.mapping_type

        if mapping_type == MigrationMappingType.REMOVED:
            continue

        if mapping_type in {MigrationMappingType.UNCHANGED, MigrationMappingType.REORDERED}:
            item = items[0]
            new_phase = updated[item.new_phase_id]
            if not _preserves_phase_meaning(old_phase, new_phase):
                continue
            failed_classification, failed_reason = classify_failed_phase_migration(old_phase, items)
            if failed_classification == "repaired":
                updated[item.new_phase_id] = new_phase.model_copy(
                    update={"status": PhaseStatus.NOT_STARTED, "failure_reasons": []}
                )
                continue
            if failed_classification == "indeterminate":
                return new_phases, MigrationOutcomeKind.PAUSE_MIGRATION, failed_reason
            if failed_classification == "still_broken":
                return new_phases, MigrationOutcomeKind.ESCALATE_MIGRATION, failed_reason
            if old_phase.status == PhaseStatus.DONE:
                updated[item.new_phase_id] = new_phase.model_copy(update={"status": PhaseStatus.DONE})
            elif old_phase.status == PhaseStatus.IN_PROGRESS:
                updated[item.new_phase_id] = new_phase.model_copy(update={"status": PhaseStatus.IN_PROGRESS})
            elif old_phase.status == PhaseStatus.BLOCKED:
                if set(old_phase.failure_reasons).issubset(WAITING_BLOCKERS):
                    updated[item.new_phase_id] = new_phase.model_copy(
                        update={
                            "status": PhaseStatus.BLOCKED,
                            "failure_reasons": list(old_phase.failure_reasons),
                        }
                    )
            continue

        if mapping_type == MigrationMappingType.SPLIT:
            target_ids = [item.new_phase_id for item in items if item.new_phase_id is not None]
            if old_phase.status in {PhaseStatus.DONE, PhaseStatus.IN_PROGRESS}:
                candidates = _split_continuation_candidates(items)
                if len(target_ids) > 1 and len(candidates) != 1:
                    return new_phases, MigrationOutcomeKind.PAUSE_MIGRATION, "split_phase_coverage_ambiguous"
                if len(candidates) == 1:
                    selected = candidates[0]
                    next_status = PhaseStatus.DONE if old_phase.status == PhaseStatus.DONE else PhaseStatus.IN_PROGRESS
                    updated[selected] = updated[selected].model_copy(update={"status": next_status})
            continue

    for new_phase_id, items in items_by_new.items():
        first_item = items[0]
        if first_item.mapping_type != MigrationMappingType.MERGED:
            continue
        source_phases = [old_by_id[item.old_phase_id] for item in items if item.old_phase_id in old_by_id]
        if any(
            source.status in {PhaseStatus.BLOCKED, PhaseStatus.FAILED}
            and source.failure_reasons
            and not set(source.failure_reasons).issubset(WAITING_BLOCKERS)
            for source in source_phases
        ):
            return new_phases, MigrationOutcomeKind.ESCALATE_MIGRATION, "merged_phase_conflict"
        if any(source.status == PhaseStatus.BLOCKED and set(source.failure_reasons).issubset(WAITING_BLOCKERS) for source in source_phases) and any(source.status == PhaseStatus.FAILED for source in source_phases):
            return new_phases, MigrationOutcomeKind.PAUSE_MIGRATION, "merged_phase_ambiguous"
        if source_phases and all(source.status == PhaseStatus.DONE for source in source_phases):
            updated[new_phase_id] = updated[new_phase_id].model_copy(update={"status": PhaseStatus.DONE})
        elif any(source.status in {PhaseStatus.DONE, PhaseStatus.IN_PROGRESS, PhaseStatus.BLOCKED} for source in source_phases):
            updated[new_phase_id] = updated[new_phase_id].model_copy(update={"status": PhaseStatus.IN_PROGRESS})

    return [updated[phase.phase_id] for phase in new_phases], None, None


def recompute_module_state(modules: list[Module], phases: list[Phase]) -> list[Module]:
    """Recompute module status and cache fields from migrated phase state."""

    phases_by_module: dict[str, list[Phase]] = defaultdict(list)
    for phase in phases:
        phases_by_module[phase.module_id].append(phase)

    recomputed: list[Module] = []
    for module in modules:
        module_phases = sorted(phases_by_module[module.module_id], key=lambda item: (item.created_at, item.phase_id))
        completed = [phase.phase_id for phase in module_phases if phase.status == PhaseStatus.DONE]
        blocked = [phase.phase_id for phase in module_phases if phase.status == PhaseStatus.BLOCKED]
        current = next(
            (
                phase.phase_id
                for phase in module_phases
                if phase.status in {PhaseStatus.IN_PROGRESS, PhaseStatus.BLOCKED, PhaseStatus.NOT_STARTED}
            ),
            None,
        )
        if module.status == ModuleStatus.OBSOLETE:
            recomputed_status = ModuleStatus.OBSOLETE
        elif module_phases and all(phase.status == PhaseStatus.DONE for phase in module_phases):
            recomputed_status = ModuleStatus.DONE
        elif any(phase.status == PhaseStatus.BLOCKED for phase in module_phases):
            recomputed_status = ModuleStatus.BLOCKED
        elif any(phase.status == PhaseStatus.IN_PROGRESS for phase in module_phases):
            recomputed_status = ModuleStatus.IN_PROGRESS
        elif any(phase.status == PhaseStatus.FAILED for phase in module_phases):
            recomputed_status = ModuleStatus.FAILED
        else:
            recomputed_status = ModuleStatus.NOT_STARTED

        recomputed.append(
            module.model_copy(
                update={
                    "status": recomputed_status,
                    "current_phase_id": current,
                    "completed_phase_ids": completed,
                    "blocked_phase_ids": blocked,
                }
            )
        )
    return recomputed


def _phase_sort_key(overview: ExperimentOverview, phase: Phase) -> tuple[int, str, int, str]:
    for module in overview.modules:
        if module.module_overview_id != phase.module_id:
            continue
        for phase_overview in module.phase_overviews:
            if phase_overview.phase_overview_id == phase.phase_id:
                return (module.sort_index, module.module_overview_id, phase_overview.sort_index, phase.phase_id)
    return (10**6, phase.module_id, 10**6, phase.phase_id)


def resolve_resume_module(modules: list[Module], phases: list[Phase], overview: ExperimentOverview) -> str:
    """Resolve the unique resume module using the required deterministic priority."""

    candidate_groups: list[list[str]] = []
    in_progress = sorted(
        {phase.module_id for phase in phases if phase.status == PhaseStatus.IN_PROGRESS},
        key=lambda module_id: _module_tie_break_key(module_id, overview),
    )
    if in_progress:
        candidate_groups.append(in_progress)

    blocked_waiting = sorted(
        {
            phase.module_id
            for phase in phases
            if phase.status == PhaseStatus.BLOCKED and set(phase.failure_reasons).issubset(WAITING_BLOCKERS)
        },
        key=lambda module_id: _module_tie_break_key(module_id, overview),
    )
    if blocked_waiting:
        candidate_groups.append(blocked_waiting)

    unfinished_by_order: list[str] = []
    for module in sorted(overview.modules, key=lambda item: (item.sort_index, item.module_overview_id)):
        module_phases = sorted(module.phase_overviews, key=lambda item: (item.sort_index, item.phase_overview_id))
        if any(
            phase.status != PhaseStatus.DONE
            for phase in phases
            if phase.module_id == module.module_overview_id and phase.phase_id in {item.phase_overview_id for item in module_phases}
        ):
            unfinished_by_order.append(module.module_overview_id)
    if unfinished_by_order:
        candidate_groups.append(sorted(set(unfinished_by_order), key=lambda module_id: _module_tie_break_key(module_id, overview)))

    for group in candidate_groups:
        if not group:
            continue
        best_key = _module_tie_break_key(group[0], overview)
        tied = [module_id for module_id in group if _module_tie_break_key(module_id, overview) == best_key]
        if len(tied) != 1:
            raise ValueError("ambiguous resume module")
        return tied[0]

    raise RuntimeError("no legal continuation point")


def _module_tie_break_key(module_id: str, overview: ExperimentOverview) -> tuple[int, str]:
    for module in overview.modules:
        if module.module_overview_id == module_id:
            return (module.sort_index, module.module_overview_id)
    return (10**6, module_id)


def resolve_resume_phase(selected_module_id: str, phases: list[Phase], overview: ExperimentOverview) -> str:
    """Resolve the unique resume phase inside the selected module."""

    module_phases = [phase for phase in phases if phase.module_id == selected_module_id]
    if not module_phases:
        raise RuntimeError("no legal continuation point")

    in_progress = sorted(
        [phase.phase_id for phase in module_phases if phase.status == PhaseStatus.IN_PROGRESS],
        key=lambda phase_id: _phase_tie_break_key(selected_module_id, phase_id, overview),
    )
    if in_progress:
        if len(in_progress) > 1 and _phase_tie_break_key(selected_module_id, in_progress[0], overview) == _phase_tie_break_key(selected_module_id, in_progress[1], overview):
            raise ValueError("ambiguous resume phase")
        ordered_phase_ids = [
            phase.phase_overview_id
            for module in sorted(overview.modules, key=lambda item: (item.sort_index, item.module_overview_id))
            if module.module_overview_id == selected_module_id
            for phase in sorted(module.phase_overviews, key=lambda item: (item.sort_index, item.phase_overview_id))
        ]
        statuses = {phase.phase_id: phase.status for phase in module_phases}
        chosen = in_progress[0]
        for phase_id in ordered_phase_ids:
            if phase_id == chosen:
                break
            if statuses.get(phase_id) != PhaseStatus.DONE:
                return phase_id
        return chosen

    blocked_waiting = sorted(
        [
            phase.phase_id
            for phase in module_phases
            if phase.status == PhaseStatus.BLOCKED and set(phase.failure_reasons).issubset(WAITING_BLOCKERS)
        ],
        key=lambda phase_id: _phase_tie_break_key(selected_module_id, phase_id, overview),
    )
    if blocked_waiting:
        if len(blocked_waiting) > 1 and _phase_tie_break_key(selected_module_id, blocked_waiting[0], overview) == _phase_tie_break_key(selected_module_id, blocked_waiting[1], overview):
            raise ValueError("ambiguous resume phase")
        return blocked_waiting[0]

    unfinished = sorted(
        [phase.phase_id for phase in module_phases if phase.status != PhaseStatus.DONE],
        key=lambda phase_id: _phase_tie_break_key(selected_module_id, phase_id, overview),
    )
    if unfinished:
        if len(unfinished) > 1 and _phase_tie_break_key(selected_module_id, unfinished[0], overview) == _phase_tie_break_key(selected_module_id, unfinished[1], overview):
            raise ValueError("ambiguous resume phase")
        return unfinished[0]

    raise RuntimeError("no legal continuation point")


def resolve_reordered_predecessor_fallback(
    *,
    selected_module_id: str,
    old_guides: list[ExecutionGuide],
    phase_mapping: list[PhaseMigrationItem],
    phases: list[Phase],
    overview: ExperimentOverview,
) -> str | None:
    """Resolve explicit reordered-predecessor fallback before generic unfinished ordering."""

    active_old_phase_ids = {
        guide.phase_id
        for guide in old_guides
        if guide.status == GuideStatus.ACTIVE and guide.module_id == selected_module_id
    }
    if not active_old_phase_ids:
        return None

    old_to_new = {
        item.old_phase_id: item.new_phase_id
        for item in phase_mapping
        if item.old_phase_id is not None
        and item.new_phase_id is not None
        and item.new_module_id == selected_module_id
        and item.mapping_type in {MigrationMappingType.UNCHANGED, MigrationMappingType.REORDERED}
    }
    current_targets = {old_to_new[phase_id] for phase_id in active_old_phase_ids if phase_id in old_to_new}
    if len(current_targets) != 1:
        return None

    current_target = next(iter(current_targets))
    ordered_phase_ids = [
        phase.phase_overview_id
        for module in sorted(overview.modules, key=lambda item: (item.sort_index, item.module_overview_id))
        if module.module_overview_id == selected_module_id
        for phase in sorted(module.phase_overviews, key=lambda item: (item.sort_index, item.phase_overview_id))
    ]
    if current_target not in ordered_phase_ids:
        return None

    statuses = {phase.phase_id: phase.status for phase in phases if phase.module_id == selected_module_id}
    predecessors = []
    for phase_id in ordered_phase_ids:
        if phase_id == current_target:
            break
        if statuses.get(phase_id) != PhaseStatus.DONE:
            predecessors.append(phase_id)

    if not predecessors:
        return None

    first_predecessor = predecessors[0]
    predecessor_lineage = {
        item.old_phase_id
        for item in phase_mapping
        if item.new_phase_id == first_predecessor and item.old_phase_id is not None
    }

    # Reordered migration must explicitly move backward to the first unfinished predecessor.
    # If that predecessor represents multiple equally viable descendants of the same old phase,
    # we pause instead of guessing by new sort order alone.
    if predecessor_lineage:
        ambiguous_predecessors = [
            phase_id
            for phase_id in predecessors
            if {
                item.old_phase_id
                for item in phase_mapping
                if item.new_phase_id == phase_id and item.old_phase_id is not None
            } == predecessor_lineage
        ]
        if len(ambiguous_predecessors) > 1:
            raise ValueError("ambiguous reordered predecessor fallback")

    return first_predecessor


def _phase_tie_break_key(module_id: str, phase_id: str, overview: ExperimentOverview) -> tuple[int, str]:
    module = next(module for module in overview.modules if module.module_overview_id == module_id)
    for phase in module.phase_overviews:
        if phase.phase_overview_id == phase_id:
            return (phase.sort_index, phase.phase_overview_id)
    return (10**6, phase_id)


def create_new_execution_guide(
    *,
    experiment_id: str,
    overview_version: int,
    module_id: str,
    phase_id: str,
    migration_id: str,
    created_at: str,
) -> ExecutionGuide:
    """Create a fresh post-migration guide only after resume resolution succeeds."""

    return ExecutionGuide(
        guide_id=f"{migration_id}:{module_id}:{phase_id}",
        experiment_id=experiment_id,
        module_id=module_id,
        phase_id=phase_id,
        overview_version=overview_version,
        guide_version=1,
        status=GuideStatus.ACTIVE,
        phase_problem="Post-migration resume point established.",
        decision_items=[],
        actions=[],
        done_criteria=[],
        blockers=[],
        fallback_rule="Stay inside the migrated phase boundary.",
        notes=["Created by migration after unique resume resolution."],
        created_from_phase_ref=phase_id,
        created_at=created_at,
        superseded_by=None,
    )


def migrate_overview(
    *,
    migration_id: str,
    old_overview: ExperimentOverview | None,
    new_overview: ExperimentOverview | None,
    old_modules: list[Module] | None,
    old_phases: list[Phase] | None,
    old_guides: list[ExecutionGuide] | None,
    old_action_records: list[ActionRecord] | None,
    module_mapping: list[ModuleMigrationItem] | None,
    phase_mapping: list[PhaseMigrationItem] | None,
    created_at: str,
) -> MigrationRunResult:
    """Run deterministic Phase 5 migration planning and routing."""

    if old_overview is None:
        raise ValueError("missing v_old overview")
    if new_overview is None:
        raise ValueError("missing v_new overview")
    if old_modules is None or old_phases is None or old_guides is None or old_action_records is None:
        raise ValueError("missing old runtime objects")

    module_mapping = module_mapping or []
    phase_mapping = phase_mapping or []

    if not module_mapping or not phase_mapping or not has_complete_mapping(old_overview, new_overview, module_mapping, phase_mapping):
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.PAUSED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.PAUSED,
            pause_reason_code="incomplete_mapping",
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.PAUSE_MIGRATION,
            migration=migration,
            old_overview=old_overview,
            new_overview=new_overview,
            old_modules=[module.model_copy() for module in old_modules],
            new_modules=[],
            old_phases=[phase.model_copy() for phase in old_phases],
            new_phases=[],
            old_guides=[guide.model_copy() for guide in old_guides],
            historical_action_records=[record.model_copy() for record in old_action_records],
            reason="incomplete_mapping",
        )

    frozen_guides, frozen_records = freeze_old_active_runtime(
        old_guides,
        old_action_records,
        migration_id=migration_id,
        to_overview_version=new_overview.version,
    )
    superseded_overview = old_overview.model_copy(update={"superseded_by_version": new_overview.version})
    prepared_new_overview = new_overview.model_copy(
        update={
            "parent_version": old_overview.version,
            "structural_change_summary": [
                f"module_mapping:{len(module_mapping)}",
                f"phase_mapping:{len(phase_mapping)}",
            ],
        }
    )

    if has_active_attempt_conflict(frozen_records):
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.ESCALATED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.ESCALATED,
            escalate_reason_code="active_attempt_conflict",
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.ESCALATE_MIGRATION,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=[module.model_copy() for module in old_modules],
            new_modules=[],
            old_phases=[phase.model_copy() for phase in old_phases],
            new_phases=[],
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason="active_attempt_conflict",
        )

    structural_reason = has_unresolved_structural_violation(prepared_new_overview, old_phases)
    if structural_reason is not None:
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.ESCALATED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.ESCALATED,
            escalate_reason_code=structural_reason,
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.ESCALATE_MIGRATION,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=[module.model_copy() for module in old_modules],
            new_modules=[],
            old_phases=[phase.model_copy() for phase in old_phases],
            new_phases=[],
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason=structural_reason,
        )

    split_ambiguity = detect_split_resume_ambiguity(old_modules, old_phases, module_mapping, phase_mapping)
    if split_ambiguity is not None:
        outcome_kind, outcome_reason = split_ambiguity
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.PAUSED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.PAUSED,
            pause_reason_code=outcome_reason,
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=outcome_kind,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=[module.model_copy() for module in old_modules],
            new_modules=[],
            old_phases=[phase.model_copy() for phase in old_phases],
            new_phases=[],
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason=outcome_reason,
        )

    new_modules = build_modules_from_overview(prepared_new_overview, module_mapping, old_modules)
    new_phases = build_phases_from_overview(prepared_new_overview)
    migrated_phases, outcome_kind, outcome_reason = handle_phase_mapping(old_phases, new_phases, phase_mapping)
    if outcome_kind is not None:
        status = MigrationStatus.PAUSED if outcome_kind == MigrationOutcomeKind.PAUSE_MIGRATION else MigrationStatus.ESCALATED
        decision = MigrationDecision.PAUSED if outcome_kind == MigrationOutcomeKind.PAUSE_MIGRATION else MigrationDecision.ESCALATED
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=status,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=decision,
            pause_reason_code=outcome_reason if outcome_kind == MigrationOutcomeKind.PAUSE_MIGRATION else None,
            escalate_reason_code=outcome_reason if outcome_kind == MigrationOutcomeKind.ESCALATE_MIGRATION else None,
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=outcome_kind,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=[module.model_copy() for module in old_modules],
            new_modules=new_modules,
            old_phases=[phase.model_copy() for phase in old_phases],
            new_phases=migrated_phases,
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason=outcome_reason,
        )

    obsolete_modules, obsolete_phases = mark_old_objects_superseded_or_obsolete(old_modules, old_phases, module_mapping, phase_mapping)
    recomputed_modules = recompute_module_state(new_modules, migrated_phases)

    current_mapping_candidates = [
        item
        for item in phase_mapping
        if item.old_phase_id in {guide.phase_id for guide in old_guides if guide.status == GuideStatus.ACTIVE}
    ]
    if any(
        guide.decision_items or guide.done_criteria
        for guide in old_guides
        if guide.status == GuideStatus.ACTIVE
    ) and any(item.mapping_type in {MigrationMappingType.SPLIT, MigrationMappingType.MERGED, MigrationMappingType.REMOVED} for item in current_mapping_candidates):
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.PAUSED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.PAUSED,
            pause_reason_code="guide_mapping_not_unique",
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.PAUSE_MIGRATION,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=obsolete_modules,
            new_modules=recomputed_modules,
            old_phases=obsolete_phases,
            new_phases=migrated_phases,
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason="guide_mapping_not_unique",
        )

    try:
        resume_module_id = resolve_resume_module(recomputed_modules, migrated_phases, prepared_new_overview)
    except ValueError:
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.PAUSED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.PAUSED,
            pause_reason_code="ambiguous_resume_module",
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.PAUSE_MIGRATION,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=obsolete_modules,
            new_modules=recomputed_modules,
            old_phases=obsolete_phases,
            new_phases=migrated_phases,
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason="ambiguous_resume_module",
        )
    except RuntimeError:
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.ESCALATED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.ESCALATED,
            escalate_reason_code="no_legal_continuation_point",
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.ESCALATE_MIGRATION,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=obsolete_modules,
            new_modules=recomputed_modules,
            old_phases=obsolete_phases,
            new_phases=migrated_phases,
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason="no_legal_continuation_point",
        )

    try:
        reordered_fallback = resolve_reordered_predecessor_fallback(
            selected_module_id=resume_module_id,
            old_guides=old_guides,
            phase_mapping=phase_mapping,
            phases=migrated_phases,
            overview=prepared_new_overview,
        )
        resume_phase_id = reordered_fallback or resolve_resume_phase(resume_module_id, migrated_phases, prepared_new_overview)
    except ValueError:
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.PAUSED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.PAUSED,
            pause_reason_code="ambiguous_resume_phase",
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.PAUSE_MIGRATION,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=obsolete_modules,
            new_modules=recomputed_modules,
            old_phases=obsolete_phases,
            new_phases=migrated_phases,
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason="ambiguous_resume_phase",
        )
    except RuntimeError:
        migration = OverviewMigration(
            migration_id=migration_id,
            experiment_id=old_overview.experiment_id,
            from_overview_version=old_overview.version,
            to_overview_version=new_overview.version,
            migration_status=MigrationStatus.ESCALATED,
            module_mapping=module_mapping,
            phase_mapping=phase_mapping,
            migration_decision=MigrationDecision.ESCALATED,
            escalate_reason_code="no_legal_continuation_point",
            created_at=created_at,
            completed_at=created_at,
        )
        return MigrationRunResult(
            kind=MigrationOutcomeKind.ESCALATE_MIGRATION,
            migration=migration,
            old_overview=superseded_overview,
            new_overview=prepared_new_overview,
            old_modules=obsolete_modules,
            new_modules=recomputed_modules,
            old_phases=obsolete_phases,
            new_phases=migrated_phases,
            old_guides=frozen_guides,
            historical_action_records=frozen_records,
            reason="no_legal_continuation_point",
        )

    new_guide = create_new_execution_guide(
        experiment_id=prepared_new_overview.experiment_id,
        overview_version=prepared_new_overview.version,
        module_id=resume_module_id,
        phase_id=resume_phase_id,
        migration_id=migration_id,
        created_at=created_at,
    )
    relinked_records = relink_historical_action_records(
        frozen_records,
        migration_id=migration_id,
        resume_module_id=resume_module_id,
        resume_phase_id=resume_phase_id,
        to_overview_version=prepared_new_overview.version,
    )
    migration = OverviewMigration(
        migration_id=migration_id,
        experiment_id=old_overview.experiment_id,
        from_overview_version=old_overview.version,
        to_overview_version=new_overview.version,
        migration_status=MigrationStatus.COMPLETED,
        module_mapping=module_mapping,
        phase_mapping=phase_mapping,
        migration_decision=MigrationDecision.AUTO_RESUMED,
        resume_module_id=resume_module_id,
        resume_phase_id=resume_phase_id,
        created_at=created_at,
        completed_at=created_at,
    )
    return MigrationRunResult(
        kind=MigrationOutcomeKind.AUTO_RESUMED,
        migration=migration,
        old_overview=superseded_overview,
        new_overview=prepared_new_overview,
        old_modules=obsolete_modules,
        new_modules=recomputed_modules,
        old_phases=obsolete_phases,
        new_phases=migrated_phases,
        old_guides=frozen_guides,
        new_guide=new_guide,
        historical_action_records=relinked_records,
        reason="auto_resumed",
    )
