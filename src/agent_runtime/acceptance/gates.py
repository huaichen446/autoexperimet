"""Pure acceptance gate evaluators for phases, modules, and experiments."""

from __future__ import annotations

from agent_runtime.models import ActionRecord, DecisionItem, DoneCheck, Module, Phase
from agent_runtime.models.common import DecisionStatus, DoneCheckStatus, ModuleStatus, PhaseStatus

from .result_types import (
    AcceptanceRoute,
    ExperimentGateKind,
    ExperimentGateResult,
    ModuleGateKind,
    ModuleGateResult,
    PhaseGateKind,
    PhaseGateResult,
)
from .validators import (
    all_required_phase_checks_met,
    all_required_phase_decisions_decided,
    decision_invalid_reason,
    done_check_invalid_reason,
    has_invalid_required_decision,
    has_illegal_decision_transition,
    is_waiting_blocked_check,
    is_waiting_blocked_decision,
    phase_state_after_satisfied,
    resolve_acceptance_failure,
)


def evaluate_phase_gate(
    phase: Phase,
    *,
    decision_items: list[DecisionItem],
    done_checks: list[DoneCheck],
    action_records: list[ActionRecord],
    current_overview_version: int,
    satisfied_state_afters: set[str] | None = None,
    current_guide_decision_ids: set[str] | None = None,
    current_guide_check_ids: set[str] | None = None,
    unresolved_skeleton_escalation: bool = False,
    would_cross_fallback_boundary: bool = False,
    illegal_transition_pairs: list[tuple[str, str]] | None = None,
) -> PhaseGateResult:
    satisfied_state_afters = satisfied_state_afters or set()
    current_guide_decision_ids = current_guide_decision_ids or set()
    current_guide_check_ids = current_guide_check_ids or set()
    illegal_transition_pairs = illegal_transition_pairs or []

    required_decisions = [
        item
        for item in decision_items
        if item.decision_scope == "phase"
        and item.required_for_phase_done
        and (item.phase_id == phase.phase_id or item.phase_id is None)
    ]
    required_checks = [
        check
        for check in done_checks
        if check.check_scope == "phase"
        and check.required
        and (check.phase_id == phase.phase_id or check.phase_id is None)
    ]
    known_record_ids = {record.action_record_id for record in action_records}

    invalid_decision_reason = next(
        (
            decision_invalid_reason(item, current_overview_version=current_overview_version)
            for item in required_decisions
            if decision_invalid_reason(item, current_overview_version=current_overview_version) is not None
        ),
        None,
    )
    illegal_transition = any(has_illegal_decision_transition(before, after) for before, after in illegal_transition_pairs)
    invalid_check_reason = next(
        (
            done_check_invalid_reason(
                check,
                current_overview_version=current_overview_version,
                known_record_ids=known_record_ids,
            )
            for check in required_checks
            if done_check_invalid_reason(
                check,
                current_overview_version=current_overview_version,
                known_record_ids=known_record_ids,
            )
            is not None
        ),
        None,
    )
    phase_conflict = (
        any(check.check_type == "state_transition" and not phase_state_after_satisfied(phase.state_after, satisfied_state_afters) for check in required_checks if check.status == DoneCheckStatus.MET)
        or phase.overview_version != current_overview_version
        or phase.status == PhaseStatus.OBSOLETE
    )
    should_escalate = any(
        [
            unresolved_skeleton_escalation,
            would_cross_fallback_boundary,
            has_invalid_required_decision(required_decisions, current_overview_version=current_overview_version),
            illegal_transition,
            invalid_check_reason is not None,
            phase_conflict,
        ]
    )
    waiting_blocked = any(is_waiting_blocked_decision(item) for item in required_decisions) or any(
        is_waiting_blocked_check(check) for check in required_checks
    )
    missing_decision_ids = [
        item.decision_id for item in required_decisions if item.status not in {DecisionStatus.DECIDED}
    ]
    missing_check_ids = [
        check.check_id for check in required_checks if check.status not in {DoneCheckStatus.MET}
    ]

    uncovered_decisions = [item.decision_id for item in required_decisions if item.decision_id not in current_guide_decision_ids]
    uncovered_checks = [check.check_id for check in required_checks if check.check_id not in current_guide_check_ids]
    state_after_met = phase_state_after_satisfied(phase.state_after, satisfied_state_afters)

    if (
        phase.status != PhaseStatus.OBSOLETE
        and all_required_phase_decisions_decided(required_decisions)
        and all_required_phase_checks_met(required_checks)
        and state_after_met
    ):
        return PhaseGateResult(kind=PhaseGateKind.PHASE_DONE)

    should_revise = bool(uncovered_decisions or uncovered_checks)
    route = resolve_acceptance_failure(
        should_escalate=should_escalate,
        should_pause=waiting_blocked,
        should_revise=should_revise,
    )
    if route == AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION:
        reason = "phase_gate_escalation"
        if invalid_decision_reason is not None:
            reason = invalid_decision_reason
        elif illegal_transition:
            reason = "illegal_decision_transition"
        elif invalid_check_reason is not None:
            reason = invalid_check_reason
        elif would_cross_fallback_boundary:
            reason = "fallback_boundary_crossing_required"
        elif phase_conflict:
            reason = "phase_structure_state_conflict"
        return PhaseGateResult(kind=PhaseGateKind.ESCALATE_TO_OVERVIEW_REVISION, reason=reason)
    if route == AcceptanceRoute.PAUSE_ACCEPTANCE:
        return PhaseGateResult(kind=PhaseGateKind.PAUSE_ACCEPTANCE, reason="waiting_blocked_acceptance")
    if route == AcceptanceRoute.REVISE_GUIDE:
        return PhaseGateResult(
            kind=PhaseGateKind.REVISE_GUIDE,
            reason="guide_coverage_insufficient",
            missing_decision_ids=missing_decision_ids,
            missing_check_ids=missing_check_ids,
        )

    return PhaseGateResult(
        kind=PhaseGateKind(route),
        reason="requirements_still_progressing" if (missing_decision_ids or missing_check_ids or not state_after_met) else "explicit_keep_current_state",
        missing_decision_ids=missing_decision_ids,
        missing_check_ids=missing_check_ids,
    )


def evaluate_module_gate(
    module: Module,
    *,
    phases: list[Phase],
    phase_results: list[PhaseGateResult],
    decision_items: list[DecisionItem],
    done_checks: list[DoneCheck],
    current_overview_version: int,
) -> ModuleGateResult:
    required_decisions = [
        item
        for item in decision_items
        if item.decision_scope == "module"
        and item.required_for_module_done
        and (item.module_id == module.module_id or item.module_id is None)
    ]
    required_checks = [
        check
        for check in done_checks
        if check.check_scope == "module"
        and check.required
        and (check.module_id == module.module_id or check.module_id is None)
    ]
    invalid_decision_reason = next(
        (
            decision_invalid_reason(item, current_overview_version=current_overview_version)
            for item in required_decisions
            if decision_invalid_reason(item, current_overview_version=current_overview_version) is not None
        ),
        None,
    )
    invalid_check_reason = next(
        (
            done_check_invalid_reason(
                check,
                current_overview_version=current_overview_version,
                known_record_ids=set(),
            )
            for check in required_checks
            if done_check_invalid_reason(
                check,
                current_overview_version=current_overview_version,
                known_record_ids=set(),
            )
            is not None
        ),
        None,
    )
    phase_result_by_id = {
        phase.phase_id: phase_results[index]
        for index, phase in enumerate(phases)
        if index < len(phase_results)
    }
    should_escalate = (
        module.overview_version != current_overview_version
        or module.status == ModuleStatus.OBSOLETE
        or any(result.kind == PhaseGateKind.ESCALATE_TO_OVERVIEW_REVISION for result in phase_results)
        or invalid_decision_reason is not None
        or invalid_check_reason is not None
    )
    waiting_blocked = any(is_waiting_blocked_decision(item) for item in required_decisions) or any(
        is_waiting_blocked_check(check) for check in required_checks
    )

    missing_phase_ids = [
        phase.phase_id
        for phase in phases
        if phase_result_by_id.get(phase.phase_id) is None or phase_result_by_id[phase.phase_id].kind != PhaseGateKind.PHASE_DONE
    ]
    missing_decision_ids = [
        item.decision_id for item in required_decisions if item.status != DecisionStatus.DECIDED
    ]
    missing_check_ids = [check.check_id for check in required_checks if check.status != DoneCheckStatus.MET]

    if not missing_phase_ids and not missing_decision_ids and not missing_check_ids:
        return ModuleGateResult(kind=ModuleGateKind.MODULE_DONE)

    should_revise = any(result.kind == PhaseGateKind.REVISE_GUIDE for result in phase_results)
    route = resolve_acceptance_failure(
        should_escalate=should_escalate,
        should_pause=waiting_blocked,
        should_revise=should_revise,
    )
    if route == AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION:
        return ModuleGateResult(
            kind=ModuleGateKind.ESCALATE_TO_OVERVIEW_REVISION,
            reason=invalid_decision_reason or invalid_check_reason or "module_gate_escalation",
        )
    if route == AcceptanceRoute.PAUSE_ACCEPTANCE:
        return ModuleGateResult(kind=ModuleGateKind.PAUSE_ACCEPTANCE, reason="waiting_blocked_acceptance")
    if route == AcceptanceRoute.REVISE_GUIDE:
        return ModuleGateResult(
            kind=ModuleGateKind.REVISE_GUIDE,
            reason="repairable_inside_current_phase",
            missing_phase_ids=missing_phase_ids,
            missing_decision_ids=missing_decision_ids,
            missing_check_ids=missing_check_ids,
        )

    return ModuleGateResult(
        kind=ModuleGateKind.KEEP_CURRENT_STATE,
        reason="requirements_still_progressing",
        missing_phase_ids=missing_phase_ids,
        missing_decision_ids=missing_decision_ids,
        missing_check_ids=missing_check_ids,
    )


def evaluate_experiment_gate(
    *,
    modules: list[Module],
    module_results: list[ModuleGateResult],
    decision_items: list[DecisionItem],
    done_checks: list[DoneCheck],
    current_overview_version: int,
    unresolved_skeleton_escalation: bool = False,
) -> ExperimentGateResult:
    required_decisions = [
        item for item in decision_items if item.decision_scope == "experiment" and item.required_for_experiment_done
    ]
    required_checks = [
        check for check in done_checks if check.check_scope == "experiment" and check.required
    ]
    invalid_decision_reason = next(
        (
            decision_invalid_reason(item, current_overview_version=current_overview_version)
            for item in required_decisions
            if decision_invalid_reason(item, current_overview_version=current_overview_version) is not None
        ),
        None,
    )
    invalid_check_reason = next(
        (
            done_check_invalid_reason(
                check,
                current_overview_version=current_overview_version,
                known_record_ids=set(),
            )
            for check in required_checks
            if done_check_invalid_reason(
                check,
                current_overview_version=current_overview_version,
                known_record_ids=set(),
            )
            is not None
        ),
        None,
    )

    module_result_by_id = {
        module.module_id: module_results[index]
        for index, module in enumerate(modules)
        if index < len(module_results)
    }
    module_conflict = any(
        module_result_by_id.get(module.module_id) is None
        or (module_result_by_id[module.module_id].kind == ModuleGateKind.MODULE_DONE and module.status == ModuleStatus.OBSOLETE)
        or (module_result_by_id[module.module_id].kind != ModuleGateKind.MODULE_DONE and module.status == ModuleStatus.DONE)
        or module.overview_version != current_overview_version
        for module in modules
    )
    should_escalate = (
        unresolved_skeleton_escalation
        or module_conflict
        or any(result.kind == ModuleGateKind.ESCALATE_TO_OVERVIEW_REVISION for result in module_results)
        or invalid_decision_reason is not None
        or invalid_check_reason is not None
    )
    waiting_blocked = any(is_waiting_blocked_decision(item) for item in required_decisions) or any(
        is_waiting_blocked_check(check) for check in required_checks
    )

    missing_module_ids = [
        module.module_id
        for module in modules
        if module_result_by_id.get(module.module_id) is None or module_result_by_id[module.module_id].kind != ModuleGateKind.MODULE_DONE
    ]
    missing_decision_ids = [
        item.decision_id for item in required_decisions if item.status != DecisionStatus.DECIDED
    ]
    missing_check_ids = [check.check_id for check in required_checks if check.status != DoneCheckStatus.MET]

    if not missing_module_ids and not missing_decision_ids and not missing_check_ids:
        return ExperimentGateResult(kind=ExperimentGateKind.EXPERIMENT_DONE)
    route = resolve_acceptance_failure(
        should_escalate=should_escalate,
        should_pause=waiting_blocked,
        should_revise=False,
    )
    if route == AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION:
        return ExperimentGateResult(
            kind=ExperimentGateKind.ESCALATE_TO_OVERVIEW_REVISION,
            reason=invalid_decision_reason or invalid_check_reason or "experiment_gate_escalation",
        )
    if route == AcceptanceRoute.PAUSE_ACCEPTANCE:
        return ExperimentGateResult(kind=ExperimentGateKind.PAUSE_ACCEPTANCE, reason="waiting_blocked_acceptance")
    return ExperimentGateResult(
        kind=ExperimentGateKind.KEEP_CURRENT_STATE,
        reason="requirements_still_progressing",
        missing_module_ids=missing_module_ids,
        missing_decision_ids=missing_decision_ids,
        missing_check_ids=missing_check_ids,
    )
