"""Focused model and inventory validation tests."""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionStatus,
    ActionType,
    DecisionItem,
    DoneCheck,
    ExecutionGuide,
    ExperimentOverview,
    GuideStatus,
    Module,
    ModuleOverview,
    ModuleStatus,
    ObjectInventory,
    Phase,
    PhaseOverview,
    PhaseStatus,
    RequiredInput,
)


def build_action() -> Action:
    return Action(
        action_id="action-1",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        overview_version=1,
        title="Read source files",
        action_type=ActionType.AUTO,
        executor_type=ActionExecutorHint.AGENT,
        instruction="Inspect the current model modules.",
        expected_output="A list of required schema gaps.",
        required_inputs=[
            RequiredInput(
                input_key="path",
                source_type="runtime_context",
                required=True,
                value_type="str",
                materialization_stage="pre_run",
            )
        ],
        decision_item_refs=["decision-1"],
        done_check_refs=["check-1"],
        expected_output_refs=["out-1"],
        retry_policy="fixed",
        max_retry=2,
        priority=10,
        declared_order=0,
        status=ActionStatus.PENDING,
        current_attempt_index=None,
        retry_count=0,
        last_failure_reason=None,
        last_blocked_reason=None,
        last_record_id=None,
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
        experiment_title="Phase 2 inventory",
        experiment_description="Protocol validation only.",
        experiment_environment="local",
        experiment_objective="Define execution protocol boundaries.",
        module_decomposition_feasibility="single_module",
        module_decomposition_rationale=["Current scope is small."],
        modules=[module_overview],
        experiment_convergence_note="Schemas import and validate.",
        failure_localization_note="Failures should stay at the schema boundary.",
        audit_status="passed",
        audit_issue_summary=[],
        audit_passed_at="2026-04-20T12:00:00Z",
        change_summary="Execution protocol definition.",
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
        status=ModuleStatus.IN_PROGRESS,
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
        status=PhaseStatus.IN_PROGRESS,
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
        status=GuideStatus.ACTIVE,
        phase_problem="Need enough context to continue.",
        decision_items=[DecisionItem(decision_id="decision-1", question="Which source should we trust first?", status="open")],
        actions=[build_action()],
        done_criteria=[DoneCheck(check_id="check-1", description="Schema boundary is documented.", status="unmet")],
        blockers=[],
        fallback_rule="Pause at phase boundary if bindings drift.",
        notes=[],
        created_from_phase_ref="phase-1",
        created_at="2026-04-20T12:00:00Z",
        superseded_by=None,
    )
    return ObjectInventory(
        experiment_overview=overview,
        modules=[module],
        phases=[phase],
        guides=[guide],
        action_records=[],
        main_doc=None,
    )


def test_model_construction_with_valid_inventory() -> None:
    inventory = build_inventory()

    assert inventory.experiment_overview.version == 1
    assert inventory.modules[0].module_overview_ref == "module-ov-1"
    assert inventory.phases[0].status == PhaseStatus.IN_PROGRESS
    assert inventory.guides[0].actions[0].status == ActionStatus.PENDING


def test_invalid_required_input_definition_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RequiredInput(
            input_key="bad",
            source_type="mystery",
            required=True,
            value_type="str",
            materialization_stage="pre_run",
        )


def test_version_boundary_enforcement_rejects_runtime_phase_version_drift() -> None:
    inventory = build_inventory()
    bad_phase = inventory.phases[0].model_copy(update={"overview_version": 2})

    with pytest.raises(ValidationError):
        ObjectInventory.model_validate({**inventory.model_dump(), "phases": [bad_phase.model_dump()]})


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
        actions=[build_action().model_copy(update={"guide_id": "guide-2"})],
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
