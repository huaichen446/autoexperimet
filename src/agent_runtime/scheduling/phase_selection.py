"""Phase-layer validation and selection within the current module."""

from __future__ import annotations

from agent_runtime.models import PhaseStatus

from .helpers import ESCALATION_REASONS, WAITING_REASONS, contains_reason, phase_repairable_locally, phases_for_module, state_after_satisfied
from .result_types import PhaseResolution, PhaseResolutionKind, SchedulerRuntimeState


def validate_current_phase(state: SchedulerRuntimeState) -> PhaseResolution:
    current = next((phase for phase in state.inventory.phases if phase.phase_id == state.current_phase_id), None)
    if current is None:
        return select_phase_within_current_module(state)
    if current.overview_version != state.inventory.experiment_overview.version:
        return PhaseResolution(
            kind=PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION,
            phase_id=current.phase_id,
            reason="version_mismatch",
        )
    if current.status == PhaseStatus.DONE:
        if state_after_satisfied(state, current):
            return select_phase_within_current_module(state)
        return PhaseResolution(
            kind=PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE,
            phase_id=current.phase_id,
            reason="state_after_unsatisfied",
        )
    if current.status == PhaseStatus.BLOCKED:
        return _route_non_happy_phase(state, current.phase_id, current.failure_reasons)
    if current.status == PhaseStatus.FAILED:
        return _route_non_happy_phase(state, current.phase_id, current.failure_reasons, default_revise="recoverable_failure")
    if current.status == PhaseStatus.OBSOLETE:
        return PhaseResolution(
            kind=PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION,
            phase_id=current.phase_id,
            reason="obsolete_phase",
        )
    return PhaseResolution(kind=PhaseResolutionKind.KEEP_CURRENT_PHASE, phase_id=current.phase_id)


def select_phase_within_current_module(state: SchedulerRuntimeState) -> PhaseResolution:
    if state.current_module_id is None:
        return PhaseResolution(
            kind=PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION,
            reason="missing_current_module",
        )
    phases = phases_for_module(state, state.current_module_id)
    current = next((phase for phase in phases if phase.phase_id == state.current_phase_id), None)
    if current is not None and current.status == PhaseStatus.DONE and state_after_satisfied(state, current):
        current_index = phases.index(current)
        for next_phase in phases[current_index + 1 :]:
            if next_phase.status != PhaseStatus.OBSOLETE:
                return PhaseResolution(kind=PhaseResolutionKind.SWITCH_PHASE, phase_id=next_phase.phase_id)
    for phase in phases:
        if phase.status in {PhaseStatus.NOT_STARTED, PhaseStatus.IN_PROGRESS}:
            return PhaseResolution(kind=PhaseResolutionKind.SWITCH_PHASE, phase_id=phase.phase_id)
        if phase.status in {PhaseStatus.BLOCKED, PhaseStatus.FAILED}:
            return _route_non_happy_phase(state, phase.phase_id, phase.failure_reasons)
    return PhaseResolution(
        kind=PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION,
        reason="no_supported_phase",
    )


def _route_non_happy_phase(
    state: SchedulerRuntimeState,
    phase_id: str,
    reasons: list[str],
    default_revise: str | None = None,
) -> PhaseResolution:
    escalation = contains_reason(reasons, ESCALATION_REASONS)
    if escalation is not None:
        return PhaseResolution(kind=PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION, phase_id=phase_id, reason=escalation)
    for blocked_reason, result_kind in WAITING_REASONS.items():
        if blocked_reason in reasons:
            return PhaseResolution(kind=PhaseResolutionKind(result_kind), phase_id=phase_id, reason=blocked_reason)
    if "guide_missing_info" in reasons:
        return PhaseResolution(kind=PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE, phase_id=phase_id, reason="guide_missing_info")
    if default_revise is not None or phase_repairable_locally(state, phase_id):
        return PhaseResolution(
            kind=PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE,
            phase_id=phase_id,
            reason=default_revise or "recoverable_failure",
        )
    return PhaseResolution(kind=PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION, phase_id=phase_id, reason="unsupported_phase_target")
