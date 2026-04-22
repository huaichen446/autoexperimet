from __future__ import annotations

from pydantic import ValidationError
import pytest

from agent_runtime.acceptance import (
    AcceptanceRoute,
    evaluate_adoption_candidate,
    evaluate_experiment_gate,
    evaluate_module_gate,
    evaluate_phase_gate,
    has_illegal_decision_transition,
    resolve_acceptance_failure,
    supersede_adopted_item,
    transition_decision_item,
)
from agent_runtime.models import (
    ActionRecord,
    ActionType,
    AdoptedDesignItem,
    AdoptionStatus,
    BlockedReason,
    DecisionItem,
    DoneCheck,
    FailureReason,
    Module,
    ModuleStatus,
    Phase,
    PhaseStatus,
    WaitingTarget,
)


def make_decision(
    decision_id: str = "decision-1",
    *,
    status: str = "open",
    scope: str = "phase",
    required_for_phase_done: bool = True,
    required_for_module_done: bool = False,
    required_for_experiment_done: bool = False,
    module_id: str | None = "module-1",
    phase_id: str | None = "phase-1",
    guide_id: str | None = "guide-1",
    selected_option: str | None = None,
    evidence_refs: list[str] | None = None,
    rationale_summary: str | None = None,
    blocker_code: str | None = None,
    overview_version: int = 1,
) -> DecisionItem:
    if scope == "module":
        phase_id = None
    if scope == "experiment":
        module_id = None
        phase_id = None
    return DecisionItem(
        decision_id=decision_id,
        experiment_id="exp-1",
        module_id=module_id,
        phase_id=phase_id,
        guide_id=guide_id,
        overview_version=overview_version,
        title=f"title-{decision_id}",
        decision_scope=scope,
        decision_type="direction",
        status=status,
        required_for_phase_done=required_for_phase_done if scope == "phase" else False,
        required_for_module_done=required_for_module_done if scope == "module" else False,
        required_for_experiment_done=required_for_experiment_done if scope == "experiment" else False,
        candidate_options=["a", "b"],
        selected_option=selected_option,
        evidence_refs=evidence_refs or [],
        rationale_summary=rationale_summary,
        blocker_code=blocker_code,
        created_at="2026-04-22T12:00:00Z",
        updated_at="2026-04-22T12:00:00Z",
        closed_at="2026-04-22T12:10:00Z" if status in {"decided", "rejected", "obsolete"} else None,
    )


def make_done_check(
    check_id: str = "check-1",
    *,
    status: str = "unmet",
    scope: str = "phase",
    required: bool = True,
    verifier_type: str | None = "evidence_based",
    verifier_config: dict | None = None,
    evidence_refs: list[str] | None = None,
    derived_from_record_ids: list[str] | None = None,
    blocked_reason_code: str | None = None,
    module_id: str | None = "module-1",
    phase_id: str | None = "phase-1",
    overview_version: int = 1,
    check_type: str = "evidence_bound",
    met_at: str | None = None,
) -> DoneCheck:
    if scope == "module":
        phase_id = None
    if scope == "experiment":
        module_id = None
        phase_id = None
    return DoneCheck(
        check_id=check_id,
        experiment_id="exp-1",
        module_id=module_id,
        phase_id=phase_id,
        guide_id="guide-1",
        overview_version=overview_version,
        check_scope=scope,
        title=f"title-{check_id}",
        check_type=check_type,
        status=status,
        required=required,
        verifier_type=verifier_type,
        verifier_config=verifier_config or {},
        evidence_refs=evidence_refs or [],
        derived_from_record_ids=derived_from_record_ids or [],
        blocked_reason_code=blocked_reason_code,
        created_at="2026-04-22T12:00:00Z",
        updated_at="2026-04-22T12:00:00Z",
        met_at=met_at or ("2026-04-22T12:15:00Z" if status == "met" else None),
    )


def make_phase(status: PhaseStatus = PhaseStatus.IN_PROGRESS, *, overview_version: int = 1) -> Phase:
    return Phase(
        phase_id="phase-1",
        module_id="module-1",
        experiment_id="exp-1",
        overview_version=overview_version,
        phase_overview_ref="phase-ov-1",
        name="Investigate",
        role="collect",
        state_after="signals gathered",
        status=status,
        is_expanded=False,
        notes=[],
        failure_reasons=[],
        retry_history=[],
        fallback_boundary="Stay inside the phase.",
        created_at="2026-04-22T12:00:00Z",
        updated_at="2026-04-22T12:00:00Z",
    )


def make_module(status: ModuleStatus = ModuleStatus.IN_PROGRESS, *, overview_version: int = 1) -> Module:
    return Module(
        module_id="module-1",
        experiment_id="exp-1",
        overview_version=overview_version,
        module_overview_ref="module-ov-1",
        name="Discovery",
        goal="Goal",
        phase_ids=["phase-1"],
        current_phase_id="phase-1",
        completed_phase_ids=[],
        blocked_phase_ids=[],
        status=status,
        notes=[],
        failure_reasons=[],
        retry_history=[],
        needs_redecomposition=False,
        created_at="2026-04-22T12:00:00Z",
        updated_at="2026-04-22T12:00:00Z",
    )


def make_record(
    record_id: str = "record-1",
    *,
    status: str = "done",
    phase_writeback_hint: str = "done",
) -> ActionRecord:
    terminal_at = "2026-04-22T12:10:00Z" if status in {"done", "failed", "abandoned"} else None
    finalized_at = "2026-04-22T12:11:00Z" if status in {"done", "failed", "abandoned"} else None
    started_at = "2026-04-22T12:05:00Z" if status in {"running", "failed", "done"} else None
    failure_reason = None
    blocked_reason = None
    waiting_target = None
    if status == "failed":
        failure_reason = FailureReason(
            category="transient_failure",
            code="failed",
            message="failed",
            retryable=False,
            counts_as_retry=False,
        )
    if status == "blocked":
        blocked_reason = BlockedReason(
            blocked_reason_type="external_tool_not_ready",
            code="blocked",
            message="blocked",
            retryable_after_unblock=True,
        )
        waiting_target = WaitingTarget(waiting_type="external_tool", target_id="target", correlation_key="corr-1")
    return ActionRecord(
        action_record_id=record_id,
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        action_id="action-1",
        overview_version=1,
        attempt_index=1,
        parent_attempt_index=None,
        action_type=ActionType.AUTO,
        executor_type="agent",
        attempt_status=status,
        finalized=status in {"done", "failed", "abandoned"},
        record_integrity="valid",
        input_snapshot={},
        execution_payload=None,
        output_snapshot={"result": "ok"} if status == "done" else None,
        result_summary=None,
        failure_reason=failure_reason,
        blocked_reason=blocked_reason,
        waiting_target=waiting_target,
        tool_request=None,
        tool_response=None,
        tool_call_status=None,
        request_target=None,
        request_payload=None,
        returned_input=None,
        evidence_refs=["evidence-1"] if status == "done" else [],
        phase_writeback_hint=phase_writeback_hint,
        counts_as_retry=False,
        selected_at="2026-04-22T12:01:00Z",
        started_at=started_at,
        terminal_at=terminal_at,
        created_at="2026-04-22T12:00:00Z",
        finalized_at=finalized_at,
        external_correlation_key=None,
        record_revision=1,
        mutation_reason_code="test",
        mutation_log_required=False,
    )


def make_adoption_candidate(
    *,
    scope: str = "phase",
    overview_version: int = 1,
    source_decision_id: str | None = "decision-1",
    source_done_check_ids: list[str] | None = None,
    source_record_ids: list[str] | None = None,
    adoption_type: str = "design_conclusion",
    evidence_refs: list[str] | None = None,
    content_snapshot: object = "snapshot",
    acceptance_basis: list[str] | None = None,
    adoption_status: AdoptionStatus = AdoptionStatus.PROPOSED,
) -> AdoptedDesignItem:
    module_id = "module-1" if scope in {"phase", "module"} else None
    phase_id = "phase-1" if scope == "phase" else None
    return AdoptedDesignItem(
        adopted_item_id="adopted-1",
        experiment_id="exp-1",
        module_id=module_id,
        phase_id=phase_id,
        guide_id="guide-1",
        overview_version=overview_version,
        source_decision_id=source_decision_id,
        source_done_check_ids=source_done_check_ids or [],
        source_record_ids=source_record_ids or ["record-1"],
        adoption_scope=scope,
        adoption_type=adoption_type,
        title="Adopt me",
        content_snapshot=content_snapshot,
        evidence_refs=["evidence-1"] if evidence_refs is None else evidence_refs,
        acceptance_basis=["gate_closed"] if acceptance_basis is None else acceptance_basis,
        adoption_status=adoption_status,
        adopted_at=None if adoption_status == AdoptionStatus.PROPOSED else "2026-04-22T12:20:00Z",
    )


def test_decision_item_schema_and_transitions() -> None:
    item = make_decision()
    assert item.status == "open"

    with pytest.raises(ValidationError):
        DecisionItem.model_validate(
            {
                "decision_id": "",
                "experiment_id": "exp-1",
                "module_id": "module-1",
                "phase_id": "phase-1",
                "overview_version": 1,
                "title": "",
                "decision_scope": "phase",
                "decision_type": "direction",
                "status": "open",
                "created_at": "2026-04-22T12:00:00Z",
                "updated_at": "2026-04-22T12:00:00Z",
            }
        )

    proposed = transition_decision_item(item, "proposed", updated_at="2026-04-22T12:01:00Z")
    assert proposed.status == "proposed"

    decided = transition_decision_item(
        proposed,
        "decided",
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="enough evidence",
        updated_at="2026-04-22T12:02:00Z",
        closed_at="2026-04-22T12:02:00Z",
    )
    assert decided.status == "decided"

    with pytest.raises(ValidationError):
        transition_decision_item(
            proposed,
            "decided",
            evidence_refs=["evidence-1"],
            rationale_summary="missing option",
            updated_at="2026-04-22T12:02:00Z",
        )

    with pytest.raises(ValidationError):
        transition_decision_item(
            proposed,
            "decided",
            selected_option="a",
            rationale_summary="missing evidence",
            updated_at="2026-04-22T12:02:00Z",
        )

    with pytest.raises(ValidationError):
        make_decision(status="blocked")

    assert has_illegal_decision_transition("decided", "open") is True
    with pytest.raises(ValueError, match="illegal_decision_transition"):
        transition_decision_item(decided, "open", updated_at="2026-04-22T12:03:00Z")


def test_done_check_schema_and_validation() -> None:
    for verifier_type, verifier_config in [
        ("record_based", {"record_count": 1}),
        ("evidence_based", {"source": "artifact"}),
        ("threshold_based", {"threshold": 1}),
        ("composite", {"all_of": ["a", "b"]}),
    ]:
        check = make_done_check(verifier_type=verifier_type, verifier_config=verifier_config)
        assert check.verifier_type == verifier_type

    met_check = make_done_check(
        status="met",
        verifier_type="evidence_based",
        verifier_config={"source": "artifact"},
        evidence_refs=["evidence-1"],
    )
    assert met_check.status == "met"

    missing_verifier = make_done_check(verifier_type=None, verifier_config={"source": "artifact"})
    invalid_result = evaluate_phase_gate(
        make_phase(),
        decision_items=[],
        done_checks=[missing_verifier],
        action_records=[],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids={"check-1"},
    )
    assert invalid_result.kind == "escalate_to_overview_revision"

    missing_config = make_done_check(verifier_config={})
    invalid_result = evaluate_phase_gate(
        make_phase(),
        decision_items=[],
        done_checks=[missing_config],
        action_records=[],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids={"check-1"},
    )
    assert invalid_result.kind == "escalate_to_overview_revision"

    missing_scope_binding = make_done_check(module_id=None, phase_id=None, verifier_config={"source": "artifact"})
    invalid_result = evaluate_phase_gate(
        make_phase(),
        decision_items=[],
        done_checks=[missing_scope_binding],
        action_records=[],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids={"check-1"},
    )
    assert invalid_result.kind == "escalate_to_overview_revision"

    blocked = make_done_check(status="blocked", blocked_reason_code="waiting_external_tool")
    assert blocked.blocked_reason_code == "waiting_external_tool"

    illegal_met = make_done_check(status="met", verifier_type="record_based", verifier_config={"record_count": 1})
    invalid_result = evaluate_phase_gate(
        make_phase(),
        decision_items=[],
        done_checks=[illegal_met],
        action_records=[],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids={"check-1"},
    )
    assert invalid_result.kind == "escalate_to_overview_revision"


def test_phase_gate_routes() -> None:
    phase = make_phase()
    decision = make_decision(
        status="decided",
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="done",
    )
    check = make_done_check(
        status="met",
        verifier_type="evidence_based",
        verifier_config={"source": "artifact"},
        evidence_refs=["evidence-1"],
    )
    result = evaluate_phase_gate(
        phase,
        decision_items=[decision],
        done_checks=[check],
        action_records=[make_record()],
        current_overview_version=1,
        satisfied_state_afters={"signals gathered"},
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert result.kind == "phase_done"

    progressing = evaluate_phase_gate(
        phase,
        decision_items=[make_decision()],
        done_checks=[make_done_check(verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert progressing.kind == "keep_current_state"

    revise = evaluate_phase_gate(
        phase,
        decision_items=[make_decision()],
        done_checks=[make_done_check(verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids=set(),
    )
    assert revise.kind == "revise_guide"

    pause = evaluate_phase_gate(
        phase,
        decision_items=[make_decision(status="blocked", blocker_code="waiting_external_tool")],
        done_checks=[make_done_check(verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert pause.kind == "pause_acceptance"

    invalid = evaluate_phase_gate(
        phase,
        decision_items=[make_decision()],
        done_checks=[make_done_check(status="invalid", verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert invalid.kind == "escalate_to_overview_revision"

    illegal_transition = evaluate_phase_gate(
        phase,
        decision_items=[make_decision()],
        done_checks=[make_done_check(verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
        illegal_transition_pairs=[("decided", "open")],
    )
    assert illegal_transition.kind == "escalate_to_overview_revision"

    conflict = evaluate_phase_gate(
        phase,
        decision_items=[decision],
        done_checks=[
            make_done_check(
                status="met",
                verifier_type="evidence_based",
                verifier_config={"source": "artifact"},
                evidence_refs=["evidence-1"],
                check_type="state_transition",
            )
        ],
        action_records=[make_record()],
        current_overview_version=1,
        satisfied_state_afters=set(),
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert conflict.kind == "escalate_to_overview_revision"


def test_required_decision_closure_integrity_escalates() -> None:
    phase = make_phase()
    check = make_done_check(verifier_config={"source": "artifact"})

    malformed_selected = make_decision(
        status="decided",
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="done",
    ).model_copy(update={"selected_option": None})
    result = evaluate_phase_gate(
        phase,
        decision_items=[malformed_selected],
        done_checks=[check],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert result.kind == "escalate_to_overview_revision"

    malformed_evidence = make_decision(
        status="decided",
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="done",
    ).model_copy(update={"evidence_refs": []})
    result = evaluate_phase_gate(
        phase,
        decision_items=[malformed_evidence],
        done_checks=[check],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert result.kind == "escalate_to_overview_revision"

    malformed_rationale = make_decision(
        status="decided",
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="done",
    ).model_copy(update={"rationale_summary": None})
    result = evaluate_phase_gate(
        phase,
        decision_items=[malformed_rationale],
        done_checks=[check],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert result.kind == "escalate_to_overview_revision"

    malformed_blocked = make_decision(
        status="blocked",
        blocker_code="waiting_external_tool",
    ).model_copy(update={"blocker_code": None})
    result = evaluate_phase_gate(
        phase,
        decision_items=[malformed_blocked],
        done_checks=[check],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert result.kind == "escalate_to_overview_revision"


def test_done_check_verifier_hardening_escalates() -> None:
    phase = make_phase()
    base_decision = make_decision()

    for verifier_config in [
        {"operator": ">=", "target_value": 1, "actual_value_source": "records"},
        {"metric_key": "count", "target_value": 1, "actual_value_source": "records"},
        {"metric_key": "count", "operator": ">=", "actual_value_source": "records"},
        {"metric_key": "count", "operator": ">=", "target_value": 1},
    ]:
        result = evaluate_phase_gate(
            phase,
            decision_items=[base_decision],
            done_checks=[make_done_check(verifier_type="threshold_based", verifier_config=verifier_config)],
            action_records=[make_record()],
            current_overview_version=1,
            current_guide_decision_ids={"decision-1"},
            current_guide_check_ids={"check-1"},
        )
        assert result.kind == "escalate_to_overview_revision"

    for verifier_config in [
        {"children": ["check-a", "check-b"]},
        {"logic": "all"},
    ]:
        result = evaluate_phase_gate(
            phase,
            decision_items=[base_decision],
            done_checks=[make_done_check(verifier_type="composite", verifier_config=verifier_config)],
            action_records=[make_record()],
            current_overview_version=1,
            current_guide_decision_ids={"decision-1"},
            current_guide_check_ids={"check-1"},
        )
        assert result.kind == "escalate_to_overview_revision"


def test_module_gate_routes() -> None:
    phase = make_phase()
    phase_done = evaluate_phase_gate(
        phase,
        decision_items=[
            make_decision(
                status="decided",
                selected_option="a",
                evidence_refs=["evidence-1"],
                rationale_summary="done",
            )
        ],
        done_checks=[
            make_done_check(
                status="met",
                verifier_type="evidence_based",
                verifier_config={"source": "artifact"},
                evidence_refs=["evidence-1"],
            )
        ],
        action_records=[make_record()],
        current_overview_version=1,
        satisfied_state_afters={"signals gathered"},
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    module_result = evaluate_module_gate(
        make_module(),
        phases=[phase],
        phase_results=[phase_done],
        decision_items=[make_decision("module-decision", scope="module", required_for_phase_done=False, required_for_module_done=True, phase_id=None, selected_option="a", evidence_refs=["evidence"], rationale_summary="done", status="decided")],
        done_checks=[make_done_check("module-check", scope="module", verifier_config={"source": "artifact"}, phase_id=None, status="met", evidence_refs=["evidence"], met_at="2026-04-22T12:15:00Z")],
        current_overview_version=1,
    )
    assert module_result.kind == "module_done"

    keep = evaluate_module_gate(
        make_module(),
        phases=[phase],
        phase_results=[phase_done.model_copy(update={"kind": "keep_current_state"})],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    )
    assert keep.kind == "keep_current_state"

    revise = evaluate_module_gate(
        make_module(),
        phases=[phase],
        phase_results=[phase_done.model_copy(update={"kind": "revise_guide"})],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    )
    assert revise.kind == "revise_guide"

    pause = evaluate_module_gate(
        make_module(),
        phases=[phase],
        phase_results=[phase_done],
        decision_items=[make_decision("module-decision", scope="module", required_for_phase_done=False, required_for_module_done=True, phase_id=None, status="blocked", blocker_code="waiting_human_input")],
        done_checks=[],
        current_overview_version=1,
    )
    assert pause.kind == "pause_acceptance"

    escalate_phase = evaluate_module_gate(
        make_module(),
        phases=[phase],
        phase_results=[phase_done.model_copy(update={"kind": "escalate_to_overview_revision"})],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    )
    assert escalate_phase.kind == "escalate_to_overview_revision"

    escalate_invalid = evaluate_module_gate(
        make_module(),
        phases=[phase],
        phase_results=[phase_done],
        decision_items=[],
        done_checks=[make_done_check("module-check", scope="module", phase_id=None, status="invalid", verifier_config={"source": "artifact"})],
        current_overview_version=1,
    )
    assert escalate_invalid.kind == "escalate_to_overview_revision"


def test_experiment_gate_routes() -> None:
    module = make_module(status=ModuleStatus.DONE)
    module_done = evaluate_module_gate(
        module,
        phases=[make_phase(status=PhaseStatus.DONE)],
        phase_results=[],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    ).model_copy(update={"kind": "module_done"})

    result = evaluate_experiment_gate(
        modules=[module],
        module_results=[module_done],
        decision_items=[
            make_decision(
                "exp-decision",
                scope="experiment",
                required_for_phase_done=False,
                required_for_experiment_done=True,
                module_id=None,
                phase_id=None,
                selected_option="a",
                evidence_refs=["evidence"],
                rationale_summary="done",
                status="decided",
            )
        ],
        done_checks=[
            make_done_check(
                "exp-check",
                scope="experiment",
                module_id=None,
                phase_id=None,
                verifier_config={"source": "artifact"},
                status="met",
                evidence_refs=["evidence"],
            )
        ],
        current_overview_version=1,
    )
    assert result.kind == "experiment_done"

    keep = evaluate_experiment_gate(
        modules=[make_module()],
        module_results=[module_done.model_copy(update={"kind": "keep_current_state"})],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    )
    assert keep.kind == "keep_current_state"

    pause = evaluate_experiment_gate(
        modules=[module],
        module_results=[module_done],
        decision_items=[
            make_decision(
                "exp-decision",
                scope="experiment",
                required_for_phase_done=False,
                required_for_experiment_done=True,
                module_id=None,
                phase_id=None,
                status="blocked",
                blocker_code="waiting_external_resource",
            )
        ],
        done_checks=[],
        current_overview_version=1,
    )
    assert pause.kind == "pause_acceptance"

    invalid = evaluate_experiment_gate(
        modules=[module],
        module_results=[module_done],
        decision_items=[],
        done_checks=[make_done_check("exp-check", scope="experiment", module_id=None, phase_id=None, status="invalid", verifier_config={"source": "artifact"})],
        current_overview_version=1,
    )
    assert invalid.kind == "escalate_to_overview_revision"

    conflict = evaluate_experiment_gate(
        modules=[make_module(status=ModuleStatus.DONE)],
        module_results=[module_done.model_copy(update={"kind": "keep_current_state"})],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    )
    assert conflict.kind == "escalate_to_overview_revision"


def test_adoption_and_promotion_rules() -> None:
    phase_gate = evaluate_phase_gate(
        make_phase(),
        decision_items=[
            make_decision(
                status="decided",
                selected_option="a",
                evidence_refs=["evidence-1"],
                rationale_summary="done",
            )
        ],
        done_checks=[
            make_done_check(
                status="met",
                verifier_type="evidence_based",
                verifier_config={"source": "artifact"},
                evidence_refs=["evidence-1"],
            )
        ],
        action_records=[make_record()],
        current_overview_version=1,
        satisfied_state_afters={"signals gathered"},
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    module_gate = evaluate_module_gate(
        make_module(),
        phases=[make_phase()],
        phase_results=[phase_gate],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    ).model_copy(update={"kind": "module_done"})
    experiment_gate = evaluate_experiment_gate(
        modules=[make_module(status=ModuleStatus.DONE)],
        module_results=[module_gate],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    ).model_copy(update={"kind": "experiment_done"})

    decision = make_decision(
        status="decided",
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="done",
    )
    check = make_done_check(
        status="met",
        verifier_type="evidence_based",
        verifier_config={"source": "artifact"},
        evidence_refs=["evidence-1"],
    )
    record = make_record()

    assert evaluate_adoption_candidate(
        make_adoption_candidate(scope="phase"),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[record],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "adopted"

    assert evaluate_adoption_candidate(
        make_adoption_candidate(scope="module"),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[record],
        current_overview_version=1,
        module_gate_result=module_gate,
    ).kind == "adopted"

    assert evaluate_adoption_candidate(
        make_adoption_candidate(scope="experiment"),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[record],
        current_overview_version=1,
        experiment_gate_result=experiment_gate,
    ).kind == "adopted"

    assert evaluate_adoption_candidate(
        make_adoption_candidate(evidence_refs=[]),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[record],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    assert evaluate_adoption_candidate(
        make_adoption_candidate(content_snapshot=""),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[record],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    assert evaluate_adoption_candidate(
        make_adoption_candidate(acceptance_basis=[]),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[record],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    assert evaluate_adoption_candidate(
        make_adoption_candidate(),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[make_record(status="failed", phase_writeback_hint="failed")],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    assert evaluate_adoption_candidate(
        make_adoption_candidate(adoption_type="notes_only_output"),
        source_decisions=[decision],
        source_done_checks=[check],
        source_records=[record],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    old_item = make_adoption_candidate(adoption_status=AdoptionStatus.ADOPTED)
    superseded = supersede_adopted_item(old_item, adopted_at="2026-04-22T12:30:00Z")
    assert old_item.adoption_status == AdoptionStatus.ADOPTED
    assert superseded.adoption_status == AdoptionStatus.SUPERSEDED
    assert make_adoption_candidate(overview_version=2).overview_version == 2


def test_adoption_binding_tightening_and_supersede_behavior() -> None:
    phase_gate = evaluate_phase_gate(
        make_phase(),
        decision_items=[
            make_decision(
                status="decided",
                selected_option="a",
                evidence_refs=["evidence-1"],
                rationale_summary="done",
            )
        ],
        done_checks=[
            make_done_check(
                status="met",
                verifier_type="evidence_based",
                verifier_config={"source": "artifact"},
                evidence_refs=["evidence-1"],
            )
        ],
        action_records=[make_record()],
        current_overview_version=1,
        satisfied_state_afters={"signals gathered"},
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    module_gate = evaluate_module_gate(
        make_module(),
        phases=[make_phase()],
        phase_results=[phase_gate],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    ).model_copy(update={"kind": "module_done"})

    phase_candidate = make_adoption_candidate(scope="phase")
    wrong_version_decision = make_decision(
        status="decided",
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="done",
        overview_version=2,
    )
    assert evaluate_adoption_candidate(
        phase_candidate,
        source_decisions=[wrong_version_decision],
        source_done_checks=[],
        source_records=[make_record()],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    module_scope_decision = make_decision(
        "module-decision",
        scope="module",
        required_for_phase_done=False,
        required_for_module_done=True,
        selected_option="a",
        evidence_refs=["evidence-1"],
        rationale_summary="done",
        status="decided",
    )
    assert evaluate_adoption_candidate(
        phase_candidate.model_copy(update={"source_decision_id": "module-decision"}),
        source_decisions=[module_scope_decision],
        source_done_checks=[],
        source_records=[make_record()],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    module_candidate = make_adoption_candidate(scope="module", source_decision_id=None, source_done_check_ids=["module-check"])
    phase_scope_check = make_done_check(
        "module-check",
        scope="phase",
        module_id="module-2",
        status="met",
        verifier_type="evidence_based",
        verifier_config={"source": "artifact"},
        evidence_refs=["evidence-1"],
    )
    wrong_version_module_check = make_done_check(
        "module-check",
        scope="module",
        phase_id=None,
        overview_version=2,
        status="met",
        verifier_type="evidence_based",
        verifier_config={"source": "artifact"},
        evidence_refs=["evidence-1"],
    )
    assert evaluate_adoption_candidate(
        module_candidate,
        source_decisions=[],
        source_done_checks=[phase_scope_check],
        source_records=[make_record()],
        current_overview_version=1,
        module_gate_result=module_gate,
    ).kind == "rejected"
    assert evaluate_adoption_candidate(
        module_candidate,
        source_decisions=[],
        source_done_checks=[wrong_version_module_check],
        source_records=[make_record()],
        current_overview_version=1,
        module_gate_result=module_gate,
    ).kind == "rejected"

    wrong_scope_record = make_record().model_copy(update={"phase_id": "phase-2"})
    assert evaluate_adoption_candidate(
        phase_candidate,
        source_decisions=[
            make_decision(
                status="decided",
                selected_option="a",
                evidence_refs=["evidence-1"],
                rationale_summary="done",
            )
        ],
        source_done_checks=[],
        source_records=[wrong_scope_record],
        current_overview_version=1,
        phase_gate_result=phase_gate,
    ).kind == "rejected"

    old_item = make_adoption_candidate(
        adoption_status=AdoptionStatus.ADOPTED,
        content_snapshot={"version": 1, "content": "old"},
    )
    old_snapshot = old_item.content_snapshot
    superseded = supersede_adopted_item(old_item, adopted_at="2026-04-22T12:30:00Z")
    new_item = make_adoption_candidate(content_snapshot={"version": 2, "content": "new"})
    assert superseded.adoption_status == AdoptionStatus.SUPERSEDED
    assert old_item.content_snapshot == old_snapshot
    assert new_item is not old_item
    assert new_item.content_snapshot != old_snapshot


def test_acceptance_routing_priority_and_safety() -> None:
    assert resolve_acceptance_failure(should_escalate=True, should_pause=True, should_revise=True) == AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION
    assert resolve_acceptance_failure(should_escalate=False, should_pause=True, should_revise=True) == AcceptanceRoute.PAUSE_ACCEPTANCE
    assert resolve_acceptance_failure(should_escalate=False, should_pause=False, should_revise=True) == AcceptanceRoute.REVISE_GUIDE

    result = evaluate_phase_gate(
        make_phase(),
        decision_items=[],
        done_checks=[],
        action_records=[],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids=set(),
    )
    assert result.kind == "keep_current_state"
    assert result.reason is not None

    module = make_module()
    before = module.model_dump()
    evaluate_module_gate(
        module,
        phases=[make_phase()],
        phase_results=[result],
        decision_items=[],
        done_checks=[],
        current_overview_version=1,
    )
    assert module.model_dump() == before

    escalate_over_pause = evaluate_phase_gate(
        make_phase(),
        decision_items=[make_decision(status="blocked", blocker_code="waiting_external_tool").model_copy(update={"overview_version": 2})],
        done_checks=[make_done_check(verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids={"decision-1"},
        current_guide_check_ids={"check-1"},
    )
    assert escalate_over_pause.kind == "escalate_to_overview_revision"

    pause_over_revise = evaluate_phase_gate(
        make_phase(),
        decision_items=[make_decision(status="blocked", blocker_code="waiting_external_tool")],
        done_checks=[make_done_check(verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids=set(),
    )
    assert pause_over_revise.kind == "pause_acceptance"

    revise_over_keep = evaluate_phase_gate(
        make_phase(),
        decision_items=[make_decision()],
        done_checks=[make_done_check(verifier_config={"source": "artifact"})],
        action_records=[make_record()],
        current_overview_version=1,
        current_guide_decision_ids=set(),
        current_guide_check_ids={"check-1"},
    )
    assert revise_over_keep.kind == "revise_guide"
