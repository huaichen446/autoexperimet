"""Shared helpers for scheduler layer resolution."""

from __future__ import annotations

from collections.abc import Iterable

from agent_runtime.execution import compute_retry_count_from_records, latest_valid_record_for_action
from agent_runtime.models import Action, ActionRecord, ActionStatus, DoneCheckStatus, Module, Phase

from .result_types import SchedulerRuntimeState


ESCALATION_REASONS = {"undeclared_dependency", "fallback_boundary_violation", "version_mismatch"}
REVISE_REASONS = {"guide_missing_info", "state_after_unsatisfied", "recoverable_failure", "missing_guide"}
WAITING_REASONS = {
    "external_tool_not_ready": "pause_wait_external_tool_result",
    "human_input_missing": "pause_wait_human_input",
    "external_resource_not_ready": "pause_wait_external_resource",
}
SKELETON_DEFECT_REASONS = ESCALATION_REASONS | {"skeleton_inconsistency", "unsupported_phase_target"}


def modules_by_id(state: SchedulerRuntimeState) -> dict[str, Module]:
    return {module.module_id: module for module in state.inventory.modules}


def phases_by_id(state: SchedulerRuntimeState) -> dict[str, Phase]:
    return {phase.phase_id: phase for phase in state.inventory.phases}


def phases_for_module(state: SchedulerRuntimeState, module_id: str) -> list[Phase]:
    ordered_ids = modules_by_id(state)[module_id].phase_ids
    phase_map = phases_by_id(state)
    return [phase_map[phase_id] for phase_id in ordered_ids]


def ordered_modules(state: SchedulerRuntimeState) -> list[Module]:
    module_by_overview_ref = {module.module_overview_ref: module for module in state.inventory.modules}
    ordered_overviews = sorted(
        state.inventory.experiment_overview.modules,
        key=lambda module_overview: (module_overview.sort_index, module_overview.module_overview_id),
    )
    return [
        module_by_overview_ref[module_overview.module_overview_id]
        for module_overview in ordered_overviews
        if module_overview.module_overview_id in module_by_overview_ref
    ]


def dependency_satisfied(state: SchedulerRuntimeState, module: Module) -> bool:
    module_overview = next(
        overview for overview in state.inventory.experiment_overview.modules if overview.module_overview_id == module.module_overview_ref
    )
    completed_names = {
        candidate.name
        for candidate in state.inventory.modules
        if candidate.status.value == "done"
    }
    return set(module_overview.depends_on_module_names).issubset(completed_names)


def has_phase_candidate(state: SchedulerRuntimeState, module: Module) -> bool:
    for phase in phases_for_module(state, module.module_id):
        if phase.overview_version != state.inventory.experiment_overview.version:
            return False
        if phase.status.value not in {"done", "obsolete"}:
            return True
    return False


def module_is_waiting_blocked(state: SchedulerRuntimeState, module: Module) -> bool:
    blocked_phase_ids = set(module.blocked_phase_ids)
    if not blocked_phase_ids:
        return False
    phase_map = phases_by_id(state)
    saw_waiting = False
    for phase_id in blocked_phase_ids:
        phase = phase_map.get(phase_id)
        if phase is None:
            return False
        waiting_reason = contains_reason(phase.failure_reasons, set(WAITING_REASONS))
        if waiting_reason is None:
            return False
        saw_waiting = True
    return saw_waiting


def state_after_satisfied(state: SchedulerRuntimeState, phase: Phase) -> bool:
    return phase.state_after in state.satisfied_state_afters


def phase_repairable_locally(state: SchedulerRuntimeState, phase_id: str) -> bool:
    return phase_id in state.locally_repairable_phase_ids


def latest_truth(action: Action, records: list[ActionRecord]) -> tuple[ActionStatus, ActionRecord | None, int]:
    record = latest_valid_record_for_action(records, action.action_id)
    if record is None:
        return ActionStatus.PENDING, None, compute_retry_count_from_records(records, action.action_id)
    return ActionStatus(record.attempt_status.value), record, compute_retry_count_from_records(records, action.action_id)


def open_decision_ids(guide) -> set[str]:
    return {item.decision_id for item in guide.decision_items if item.status.value == "open"}


def unmet_done_check_ids(guide) -> set[str]:
    return {check.check_id for check in guide.done_criteria if check.status == DoneCheckStatus.UNMET}


def contains_reason(reasons: Iterable[str], reason_set: set[str]) -> str | None:
    for reason in reasons:
        if reason in reason_set:
            return reason
    return None
