"""Phase 1 model and boundary validation tests."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from agent_runtime.models import (
    Action,
    ActionRecord,
    ActionRecordStatus,
    ActionStatus,
    ActionType,
    AdoptedDesignItem,
    DecisionItem,
    DecisionStatus,
    DoneCheck,
    DoneCheckStatus,
    ExecutionGuide,
    ExperimentMainDoc,
    ExperimentOverview,
    GuideStatus,
    Module,
    ModuleOverview,
    ModuleStatus,
    ObjectInventory,
    Phase,
    PhaseStatus,
    PhaseOverview,
)


def build_inventory() -> ObjectInventory:
    phase_overview = PhaseOverview(
        phase_overview_id="phase-ov-1",
        module_overview_id="module-ov-1",
        experiment_id="exp-1",
        overview_version=1,
        name="Investigate",
        role="collect signals",
        state_after="signals gathered",
        why_phase_not_action="It groups multiple possible actions.",
        transition_to_next="Move to synthesis.",
        sort_index=0,
    )
    module_overview = ModuleOverview(
        module_overview_id="module-ov-1",
        experiment_id="exp-1",
        overview_version=1,
        name="Discovery",
        goal="Understand the current state.",
        why_independent="It can converge independently.",
        inputs=["brief"],
        outputs=["signals"],
        contribution_to_experiment="Produces validated context.",
        phase_overviews=[phase_overview],
        phase_convergence_note="Enough signals to move forward.",
        depends_on_module_names=[],
        sort_index=0,
    )
    overview = ExperimentOverview(
        overview_id="overview-1",
        experiment_id="exp-1",
        version=1,
        parent_version=None,
        experiment_title="Phase 1 inventory",
        experiment_description="Schema validation only.",
        experiment_environment="local",
        experiment_objective="Define object inventory boundaries.",
        module_decomposition_feasibility="single_module",
        module_decomposition_rationale=["Current scope is small."],
        modules=[module_overview],
        experiment_convergence_note="Schemas import and validate.",
        failure_localization_note="Failures should stay at the schema boundary.",
        audit_status="passed",
        audit_issue_summary=[],
        audit_passed_at="2026-04-20T12:00:00Z",
        change_summary="Initial boundary definition.",
        created_at="2026-04-20T11:00:00Z",
        superseded_by_version=None,
    )
    module = Module(
        module_id="module-1",
        experiment_id="exp-1",
        overview_version=1,
        module_overview_ref="module-ov-1",
        name="Discovery",
        goal="Understand the current state.",
        phase_ids=["phase-1"],
        current_phase_id="phase-1",
        completed_phase_ids=[],
        blocked_phase_ids=[],
        status="in_progress",
        notes=[],
        failure_reasons=[],
        retry_history=[],
        needs_redecomposition=False,
        created_at="2026-04-20T12:00:00Z",
        updated_at="2026-04-20T12:05:00Z",
    )
    phase = Phase(
        phase_id="phase-1",
        module_id="module-1",
        experiment_id="exp-1",
        overview_version=1,
        phase_overview_ref="phase-ov-1",
        name="Investigate",
        role="collect signals",
        state_after="signals gathered",
        status="in_progress",
        is_expanded=False,
        notes=[],
        failure_reasons=[],
        retry_history=[],
        fallback_boundary="Stay inside this phase.",
        created_at="2026-04-20T12:00:00Z",
        updated_at="2026-04-20T12:05:00Z",
    )
    guide = ExecutionGuide(
        guide_id="guide-1",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        overview_version=1,
        guide_version=1,
        status="active",
        phase_problem="Need enough context to continue.",
        decision_items=[
            DecisionItem(
                decision_id="decision-1",
                question="Which source should we trust first?",
                status="open",
            )
        ],
        actions=[
            Action(
                action_id="action-1",
                title="Read source files",
                action_type="auto",
                executor_hint="agent",
                instruction="Inspect the current model modules.",
                expected_output="A list of required schema gaps.",
                status=ActionStatus.SELECTED,
            )
        ],
        done_criteria=[
            DoneCheck(
                check_id="check-1",
                description="Schema boundary is documented.",
                status=DoneCheckStatus.UNMET,
            )
        ],
        blockers=[],
        fallback_rule="Pause at phase boundary if bindings drift.",
        notes=[],
        created_from_phase_ref="phase-1",
        created_at="2026-04-20T12:00:00Z",
        superseded_by=None,
    )
    record = ActionRecord(
        action_record_id="record-1",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        overview_version=1,
        guide_id="guide-1",
        action_id="action-1",
        action_type="auto",
        executor="agent",
        status="succeeded",
        input_snapshot={"path": "src/agent_runtime/models"},
        output_snapshot={"files": 5},
        result_summary="Collected the file inventory.",
        evidence_refs=["src/agent_runtime/models"],
        failure_reason=None,
        retry_index=0,
        started_at="2026-04-20T12:01:00Z",
        finished_at="2026-04-20T12:02:00Z",
        created_at="2026-04-20T12:00:30Z",
    )
    main_doc = ExperimentMainDoc(
        doc_id="doc-1",
        experiment_id="exp-1",
        adopted_design_items=[
            AdoptedDesignItem(
                item_id="item-1",
                title="Preserve overview version boundary",
                content="Runtime objects keep overview references instead of inlining skeleton definitions.",
                source_phase_id="phase-1",
                source_guide_id="guide-1",
                source_overview_version=1,
                acceptance_basis="Captured in approved guide output.",
                accepted_at="2026-04-20T12:10:00Z",
            )
        ],
        created_at="2026-04-20T12:10:00Z",
        updated_at="2026-04-20T12:10:00Z",
    )
    return ObjectInventory(
        experiment_overview=overview,
        modules=[module],
        phases=[phase],
        guides=[guide],
        action_records=[record],
        main_doc=main_doc,
    )


def test_model_construction_with_valid_inventory() -> None:
    inventory = build_inventory()

    assert inventory.experiment_overview.version == 1
    assert inventory.modules[0].module_overview_ref == "module-ov-1"
    assert inventory.phases[0].status == PhaseStatus.IN_PROGRESS
    assert inventory.guides[0].actions[0].status == ActionStatus.SELECTED


def test_phase_status_uses_dedicated_enum() -> None:
    phase = build_inventory().phases[0]

    assert isinstance(phase.status, PhaseStatus)
    assert not isinstance(phase.status, ModuleStatus)


def test_invalid_phase_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Phase(
            phase_id="phase-1",
            module_id="module-1",
            experiment_id="exp-1",
            overview_version=1,
            phase_overview_ref="phase-ov-1",
            name="Investigate",
            role="collect signals",
            state_after="signals gathered",
            status="not_a_real_status",
            is_expanded=False,
            notes=[],
            failure_reasons=[],
            retry_history=[],
            fallback_boundary="Stay inside this phase.",
            created_at="2026-04-20T12:00:00Z",
            updated_at="2026-04-20T12:05:00Z",
        )


def test_invalid_state_rejection_for_done_check_and_decision_item() -> None:
    with pytest.raises(ValidationError):
        DoneCheck(
            check_id="check-1",
            description="Need evidence.",
            status=DoneCheckStatus.MET,
            evidence_ref=None,
        )

    with pytest.raises(ValidationError):
        DecisionItem(
            decision_id="decision-1",
            question="Did we decide?",
            status=DecisionStatus.DECIDED,
            decision="yes",
            rationale=None,
        )


def test_version_boundary_enforcement_rejects_runtime_phase_version_drift() -> None:
    inventory = build_inventory()
    bad_phase = inventory.phases[0].model_copy(update={"overview_version": 2})

    with pytest.raises(ValidationError):
        ObjectInventory.model_validate(
            {
                **inventory.model_dump(),
                "phases": [bad_phase.model_dump()],
            }
        )


def test_action_record_single_attempt_expectations() -> None:
    with pytest.raises(ValidationError):
        ActionRecord(
            action_record_id="record-1",
            experiment_id="exp-1",
            module_id="module-1",
            phase_id="phase-1",
            overview_version=1,
            guide_id="guide-1",
            action_id="action-1",
            action_type=ActionType.AUTO,
            executor="agent",
            status=ActionRecordStatus.RUNNING,
            input_snapshot={},
            output_snapshot=None,
            result_summary="Running",
            evidence_refs=[],
            failure_reason=None,
            retry_index=0,
            started_at=None,
            finished_at=None,
            created_at="2026-04-20T12:00:00Z",
        )

    with pytest.raises(ValidationError):
        ActionRecord(
            action_record_id="record-2",
            experiment_id="exp-1",
            module_id="module-1",
            phase_id="phase-1",
            overview_version=1,
            guide_id="guide-1",
            action_id="action-1",
            action_type=ActionType.AUTO,
            executor="agent",
            status=ActionRecordStatus.SUCCEEDED,
            input_snapshot={},
            output_snapshot=None,
            result_summary="Done",
            evidence_refs=[],
            failure_reason=None,
            retry_index=0,
            started_at="2026-04-20T12:00:00Z",
            finished_at="2026-04-20T12:05:00Z",
            created_at="2026-04-20T12:00:00Z",
        )


def test_execution_guide_binding_requirements() -> None:
    inventory = build_inventory()
    bad_guide = inventory.guides[0].model_copy(update={"created_from_phase_ref": "phase-x"})

    with pytest.raises(ValidationError):
        bad_guide.model_validate(bad_guide.model_dump())

    with pytest.raises(ValidationError):
        ObjectInventory.model_validate(
            {
                **inventory.model_dump(),
                "guides": [inventory.guides[0].model_copy(update={"module_id": "module-x"}).model_dump()],
            }
        )


def test_module_requires_bound_phase_inventory() -> None:
    inventory = build_inventory()

    with pytest.raises(ValidationError):
        ObjectInventory.model_validate({**inventory.model_dump(), "phases": []})


def test_action_must_belong_to_exactly_one_execution_guide() -> None:
    inventory = build_inventory()
    duplicate_action_guide = ExecutionGuide(
        guide_id="guide-2",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        overview_version=1,
        guide_version=2,
        status=GuideStatus.DRAFT,
        phase_problem="Alternative draft guide.",
        decision_items=[],
        actions=[
            Action(
                action_id="action-1",
                title="Conflicting owner",
                action_type=ActionType.AUTO,
                executor_hint="agent",
                instruction="Duplicate id on purpose.",
                expected_output="Should fail.",
                status=ActionStatus.PENDING,
            )
        ],
        done_criteria=[],
        blockers=[],
        fallback_rule="Stop.",
        notes=[],
        created_from_phase_ref="phase-1",
        created_at="2026-04-20T12:06:00Z",
        superseded_by=None,
    )

    with pytest.raises(ValidationError):
        ObjectInventory.model_validate(
            {
                **inventory.model_dump(),
                "guides": [*(guide.model_dump() for guide in inventory.guides), duplicate_action_guide.model_dump()],
            }
        )


def test_archive_relationships_require_existing_sources() -> None:
    inventory = build_inventory()
    bad_doc = inventory.main_doc.model_copy(
        update={
            "adopted_design_items": [
                inventory.main_doc.adopted_design_items[0].model_copy(update={"source_phase_id": "phase-x"})
            ]
        }
    )

    with pytest.raises(ValidationError):
        ObjectInventory.model_validate({**inventory.model_dump(), "main_doc": bad_doc.model_dump()})
