"""Small validation and routing helpers for the acceptance layer."""

from __future__ import annotations

from agent_runtime.models import ActionRecord, DecisionItem, DoneCheck
from agent_runtime.models.common import ActionRecordStatus, DecisionStatus, DoneCheckStatus

from .result_types import AcceptanceRoute


WAITING_BLOCKER_CODES = {
    "waiting_external_tool",
    "waiting_human_input",
    "waiting_external_resource",
}


NON_PROMOTABLE_ADOPTION_TYPES = {
    "notes_only_output",
    "local_observation",
    "background_info",
    "temporary_comparison",
    "candidate_option",
    "intermediate_output",
    "guide_revision_only",
}


def resolve_acceptance_failure(*, should_escalate: bool, should_pause: bool, should_revise: bool) -> AcceptanceRoute:
    if should_escalate:
        return AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION
    if should_pause:
        return AcceptanceRoute.PAUSE_ACCEPTANCE
    if should_revise:
        return AcceptanceRoute.REVISE_GUIDE
    return AcceptanceRoute.KEEP_CURRENT_STATE


def has_illegal_decision_transition(previous_status: str, next_status: str) -> bool:
    allowed = {
        DecisionStatus.OPEN: {DecisionStatus.PROPOSED, DecisionStatus.BLOCKED, DecisionStatus.OBSOLETE},
        DecisionStatus.PROPOSED: {DecisionStatus.DECIDED, DecisionStatus.REJECTED, DecisionStatus.OBSOLETE},
        DecisionStatus.BLOCKED: {DecisionStatus.OPEN, DecisionStatus.PROPOSED},
        DecisionStatus.DECIDED: set(),
        DecisionStatus.REJECTED: set(),
        DecisionStatus.OBSOLETE: set(),
    }
    return DecisionStatus(next_status) not in allowed[DecisionStatus(previous_status)]


def transition_decision_item(
    item: DecisionItem,
    next_status: str,
    **updates: object,
) -> DecisionItem:
    if has_illegal_decision_transition(item.status, next_status):
        raise ValueError("illegal_decision_transition")
    payload = item.model_dump()
    payload.update(updates)
    payload["status"] = next_status
    return DecisionItem.model_validate(payload)


def required_for_scope(item: DecisionItem | DoneCheck, scope: str) -> bool:
    if isinstance(item, DecisionItem):
        return {
            "phase": item.required_for_phase_done,
            "module": item.required_for_module_done,
            "experiment": item.required_for_experiment_done,
        }[scope]
    return item.required


def is_waiting_blocked_decision(item: DecisionItem) -> bool:
    return item.status == DecisionStatus.BLOCKED and item.blocker_code in WAITING_BLOCKER_CODES


def is_waiting_blocked_check(check: DoneCheck) -> bool:
    return check.status == DoneCheckStatus.BLOCKED and check.blocked_reason_code in WAITING_BLOCKER_CODES


def decision_invalid_reason(
    item: DecisionItem,
    *,
    current_overview_version: int,
) -> str | None:
    if item.overview_version != current_overview_version:
        return "overview_version_mismatch"
    if not item.experiment_id:
        return "missing_experiment_binding"
    if item.decision_scope == "phase" and (not item.module_id or not item.phase_id):
        return "required_scope_binding_missing"
    if item.decision_scope == "module" and not item.module_id:
        return "required_scope_binding_missing"
    if item.status == DecisionStatus.DECIDED:
        if not item.selected_option:
            return "decided_missing_selected_option"
        if not item.evidence_refs:
            return "decided_missing_evidence_refs"
        if not item.rationale_summary:
            return "decided_missing_rationale_summary"
    if item.status == DecisionStatus.BLOCKED and not item.blocker_code:
        return "blocked_missing_blocker_code"
    return None


def has_invalid_required_decision(
    decisions: list[DecisionItem],
    *,
    current_overview_version: int,
) -> bool:
    return any(
        decision_invalid_reason(item, current_overview_version=current_overview_version) is not None
        for item in decisions
    )


def done_check_invalid_reason(
    check: DoneCheck,
    *,
    current_overview_version: int,
    known_record_ids: set[str],
) -> str | None:
    if check.overview_version != current_overview_version:
        return "overview_version_mismatch"
    if check.required and check.check_scope == "phase" and (not check.module_id or not check.phase_id):
        return "required_scope_binding_missing"
    if check.required and check.check_scope == "module" and not check.module_id:
        return "required_scope_binding_missing"
    if not check.verifier_type:
        return "missing_verifier_type"
    if check.verifier_type not in {"record_based", "evidence_based", "threshold_based", "composite"}:
        return "missing_verifier_type"
    if not check.verifier_config:
        return "missing_verifier_config"
    if check.verifier_type == "threshold_based" and not {
        "metric_key",
        "operator",
        "target_value",
        "actual_value_source",
    }.issubset(check.verifier_config):
        return "threshold_config_incomplete"
    if check.verifier_type == "composite" and not {"logic", "children"}.issubset(check.verifier_config):
        return "composite_config_incomplete"
    if any(record_id not in known_record_ids for record_id in check.derived_from_record_ids):
        return "referenced_object_missing"
    if check.status == DoneCheckStatus.MET and not has_valid_done_check_basis(check, known_record_ids=known_record_ids):
        return "met_without_valid_basis"
    if check.status == DoneCheckStatus.INVALID:
        return "explicit_invalid"
    return None


def has_invalid_required_done_check(
    checks: list[DoneCheck],
    *,
    current_overview_version: int,
    known_record_ids: set[str],
) -> bool:
    return any(
        check.required and done_check_invalid_reason(
            check,
            current_overview_version=current_overview_version,
            known_record_ids=known_record_ids,
        )
        for check in checks
    )


def has_valid_done_check_basis(check: DoneCheck, *, known_record_ids: set[str]) -> bool:
    if check.verifier_type == "record_based":
        return bool(check.derived_from_record_ids) and set(check.derived_from_record_ids).issubset(known_record_ids)
    if check.verifier_type == "evidence_based":
        return bool(check.evidence_refs)
    if check.verifier_type == "threshold_based":
        return {
            "metric_key",
            "operator",
            "target_value",
            "actual_value_source",
        }.issubset(check.verifier_config)
    if check.verifier_type == "composite":
        return {"logic", "children"}.issubset(check.verifier_config) and bool(check.verifier_config["children"])
    return False


def all_required_phase_decisions_decided(decisions: list[DecisionItem]) -> bool:
    return all(item.status == DecisionStatus.DECIDED for item in decisions if item.required_for_phase_done)


def all_required_phase_checks_met(checks: list[DoneCheck]) -> bool:
    return all(check.status == DoneCheckStatus.MET for check in checks if check.required)


def phase_state_after_satisfied(phase_state_after: str, satisfied_state_afters: set[str]) -> bool:
    return phase_state_after in satisfied_state_afters


def candidate_has_evidence(evidence_refs: list[str]) -> bool:
    return bool(evidence_refs)


def candidate_has_acceptance_basis(acceptance_basis: list[str]) -> bool:
    return bool(acceptance_basis)


def candidate_has_content_snapshot(content_snapshot: object) -> bool:
    if isinstance(content_snapshot, str):
        return bool(content_snapshot.strip())
    if isinstance(content_snapshot, (list, dict)):
        return bool(content_snapshot)
    return content_snapshot is not None


def candidate_is_temporary_or_blocked(adoption_type: str, source_records: list[ActionRecord]) -> bool:
    if adoption_type in NON_PROMOTABLE_ADOPTION_TYPES:
        return True
    for record in source_records:
        if record.attempt_status != ActionRecordStatus.DONE:
            return True
        if record.phase_writeback_hint in {"notes_only", "blocked", "failed", "in_progress"}:
            return True
    return False
