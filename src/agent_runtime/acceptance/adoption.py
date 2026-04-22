"""Promotion logic for adopted design items."""

from __future__ import annotations

from agent_runtime.models import ActionRecord, AdoptedDesignItem, DecisionItem, DoneCheck
from agent_runtime.models.common import AdoptionStatus, DecisionStatus, DoneCheckStatus

from .result_types import AdoptionEvaluation, AdoptionEvaluationKind, ExperimentGateResult, ModuleGateResult, PhaseGateResult
from .validators import (
    candidate_has_acceptance_basis,
    candidate_has_content_snapshot,
    candidate_has_evidence,
    candidate_is_temporary_or_blocked,
)


def evaluate_adoption_candidate(
    candidate: AdoptedDesignItem,
    *,
    source_decisions: list[DecisionItem],
    source_done_checks: list[DoneCheck],
    source_records: list[ActionRecord],
    current_overview_version: int,
    phase_gate_result: PhaseGateResult | None = None,
    module_gate_result: ModuleGateResult | None = None,
    experiment_gate_result: ExperimentGateResult | None = None,
    adopted_at: str = "1970-01-01T00:00:00Z",
) -> AdoptionEvaluation:
    if candidate.overview_version != current_overview_version:
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="overview_version_conflict")
    if not candidate_has_evidence(candidate.evidence_refs):
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="missing_evidence_refs")
    if not candidate_has_content_snapshot(candidate.content_snapshot):
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="missing_content_snapshot")
    if not candidate_has_acceptance_basis(candidate.acceptance_basis):
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="missing_acceptance_basis")
    if candidate_is_temporary_or_blocked(candidate.adoption_type, source_records):
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="non_promotable_execution_layer_output")

    scope_gate_closed = {
        "phase": phase_gate_result is not None and phase_gate_result.kind == "phase_done",
        "module": module_gate_result is not None and module_gate_result.kind == "module_done",
        "experiment": experiment_gate_result is not None and experiment_gate_result.kind == "experiment_done",
    }[candidate.adoption_scope]
    if not scope_gate_closed:
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="scope_gate_not_closed")

    bound_decision = _resolve_bound_decision(
        candidate=candidate,
        source_decisions=source_decisions,
        current_overview_version=current_overview_version,
    )
    bound_checks = [
        check
        for check in source_done_checks
        if check.check_id in candidate.source_done_check_ids
        and check.required
        and check.status == DoneCheckStatus.MET
        and _scope_matches_candidate(
            candidate_scope=candidate.adoption_scope,
            candidate_module_id=candidate.module_id,
            candidate_phase_id=candidate.phase_id,
            source_scope=check.check_scope,
            source_module_id=check.module_id,
            source_phase_id=check.phase_id,
        )
        and check.experiment_id == candidate.experiment_id
        and check.overview_version == current_overview_version
    ]
    bound_records = [
        record
        for record in source_records
        if record.action_record_id in candidate.source_record_ids
        and record.experiment_id == candidate.experiment_id
        and record.overview_version == current_overview_version
        and _record_matches_candidate(candidate, record)
    ]
    if candidate.source_record_ids and len(bound_records) != len(candidate.source_record_ids):
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="source_record_scope_mismatch")
    if not bound_decision and not bound_checks:
        return AdoptionEvaluation(kind=AdoptionEvaluationKind.REJECTED, reason="missing_closed_acceptance_binding")

    adopted_item = candidate.model_copy(update={"adoption_status": AdoptionStatus.ADOPTED, "adopted_at": adopted_at})
    return AdoptionEvaluation(kind=AdoptionEvaluationKind.ADOPTED, adopted_item=adopted_item)


def supersede_adopted_item(item: AdoptedDesignItem, *, adopted_at: str) -> AdoptedDesignItem:
    return item.model_copy(update={"adoption_status": AdoptionStatus.SUPERSEDED, "adopted_at": adopted_at})


def _resolve_bound_decision(
    *,
    candidate: AdoptedDesignItem,
    source_decisions: list[DecisionItem],
    current_overview_version: int,
) -> bool:
    if not candidate.source_decision_id:
        return False
    for decision in source_decisions:
        if decision.decision_id != candidate.source_decision_id:
            continue
        if decision.status != DecisionStatus.DECIDED:
            continue
        if decision.experiment_id != candidate.experiment_id:
            continue
        if decision.overview_version != current_overview_version:
            continue
        if _scope_matches_candidate(
            candidate_scope=candidate.adoption_scope,
            candidate_module_id=candidate.module_id,
            candidate_phase_id=candidate.phase_id,
            source_scope=decision.decision_scope,
            source_module_id=decision.module_id,
            source_phase_id=decision.phase_id,
        ):
            return True
    return False


def _scope_matches_candidate(
    *,
    candidate_scope: str,
    candidate_module_id: str | None,
    candidate_phase_id: str | None,
    source_scope: str,
    source_module_id: str | None,
    source_phase_id: str | None,
) -> bool:
    if candidate_scope == "phase":
        return (
            source_scope == "phase"
            and candidate_module_id == source_module_id
            and candidate_phase_id == source_phase_id
        )
    if candidate_scope == "module":
        if source_scope == "module":
            return candidate_module_id == source_module_id and source_phase_id is None
        if source_scope == "phase":
            return candidate_module_id == source_module_id
        return False
    if source_scope == "experiment":
        return source_module_id is None and source_phase_id is None
    return True


def _record_matches_candidate(candidate: AdoptedDesignItem, record: ActionRecord) -> bool:
    if candidate.adoption_scope == "phase":
        return record.module_id == candidate.module_id and record.phase_id == candidate.phase_id
    if candidate.adoption_scope == "module":
        return record.module_id == candidate.module_id
    return True
