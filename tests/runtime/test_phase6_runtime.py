from __future__ import annotations

from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionType,
    AdoptedDesignItem,
    AdoptionStatus,
    AuditStatus,
    ExecutionGuide,
    ExperimentOverview,
    GuideStatus,
    Module,
    ModuleOverview,
    ModuleStatus,
    Phase,
    PhaseOverview,
    PhaseStatus,
)
from agent_runtime.runtime import (
    AcceptanceEvaluationResult,
    ExecutionWritebackResult,
    RuntimeMigrationKind,
    RuntimeMigrationResult,
    RuntimeServices,
    RuntimeStatus,
    handle_acceptance_result,
    handle_action_result,
    handle_guide_result,
    handle_module_result,
    handle_phase_result,
    initialize_runtime_state,
    is_terminal_status,
    old_guides_inactive_after_migration,
    run_experiment_runtime,
    run_runtime,
)
from agent_runtime.scheduling import (
    ActionResolution,
    ActionResolutionKind,
    GuideResolution,
    GuideResolutionKind,
    ModuleResolution,
    ModuleResolutionKind,
    PhaseResolution,
    PhaseResolutionKind,
)


NOW = "2026-04-24T10:00:00Z"


def make_overview(*, version: int = 1, module_id: str = "module-1", phase_id: str = "phase-1") -> ExperimentOverview:
    phase = PhaseOverview(
        phase_overview_id=phase_id,
        module_overview_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        name="Phase",
        role="do work",
        state_after=f"state-{phase_id}",
        why_phase_not_action="Needs round control.",
        transition_to_next="Continue linearly.",
        sort_index=0,
    )
    module = ModuleOverview(
        module_overview_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        name="Module",
        goal="Goal",
        why_independent="Small unit.",
        inputs=[],
        outputs=[],
        contribution_to_experiment="Contributes.",
        phase_overviews=[phase],
        phase_convergence_note="Done when state exists.",
        sort_index=0,
    )
    return ExperimentOverview(
        overview_id=f"overview-{version}",
        experiment_id="exp-1",
        version=version,
        experiment_title="Runtime",
        experiment_description="Runtime tests.",
        experiment_objective="Complete.",
        module_decomposition_feasibility="single_module",
        modules=[module],
        experiment_convergence_note="All modules done.",
        failure_localization_note="Localize narrowly.",
        audit_status=AuditStatus.PASSED,
        audit_passed_at=NOW,
        created_at=NOW,
    )


def make_module(module_id: str = "module-1", *, version: int = 1, status: ModuleStatus = ModuleStatus.IN_PROGRESS) -> Module:
    return Module(
        module_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        module_overview_ref=module_id,
        name="Module",
        goal="Goal",
        phase_ids=["phase-1" if module_id == "module-1" else "phase-2"],
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def make_phase(
    phase_id: str = "phase-1",
    *,
    module_id: str = "module-1",
    version: int = 1,
    status: PhaseStatus = PhaseStatus.IN_PROGRESS,
) -> Phase:
    return Phase(
        phase_id=phase_id,
        module_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        phase_overview_ref=phase_id,
        name="Phase",
        role="role",
        state_after=f"state-{phase_id}",
        status=status,
        fallback_boundary="Stay inside phase.",
        created_at=NOW,
        updated_at=NOW,
    )


def make_action(action_id: str = "action-1", *, guide_id: str = "guide-1", version: int = 1) -> Action:
    return Action(
        action_id=action_id,
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id=guide_id,
        overview_version=version,
        title="Action",
        action_type=ActionType.AUTO,
        executor_type=ActionExecutorHint.AGENT,
        instruction="Do it.",
        expected_output="Output.",
        retry_policy="fixed",
        max_retry=1,
        declared_order=0,
    )


def make_guide(guide_id: str = "guide-1", *, version: int = 1, actions: list[Action] | None = None) -> ExecutionGuide:
    return ExecutionGuide(
        guide_id=guide_id,
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        overview_version=version,
        guide_version=1,
        status=GuideStatus.ACTIVE,
        phase_problem="Need work.",
        actions=actions if actions is not None else [make_action(guide_id=guide_id, version=version)],
        fallback_rule="Stay inside phase.",
        created_from_phase_ref="phase-1",
        created_at=NOW,
    )


def make_adopted_item() -> AdoptedDesignItem:
    return AdoptedDesignItem(
        adopted_item_id="adopted-1",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        overview_version=1,
        adoption_scope="phase",
        adoption_type="design_conclusion",
        title="Adopted",
        content_snapshot={"value": "kept"},
        evidence_refs=["evidence-1"],
        acceptance_basis=["phase_done"],
        adoption_status=AdoptionStatus.ADOPTED,
        adopted_at=NOW,
    )


def make_state():
    overview = make_overview()
    state = initialize_runtime_state(
        overview=overview,
        modules=[make_module()],
        phases=[make_phase()],
        guides=[make_guide()],
    )
    state.current_module_id = "module-1"
    state.current_phase_id = "phase-1"
    state.current_guide_id = "guide-1"
    state.current_action_id = "action-1"
    return state


def auto_migration_state() -> RuntimeMigrationResult:
    overview = make_overview(version=2, module_id="module-2", phase_id="phase-2")
    module = make_module("module-2", version=2)
    phase = make_phase("phase-2", module_id="module-2", version=2)
    return RuntimeMigrationResult(
        kind=RuntimeMigrationKind.AUTO_RESUMED,
        overview=overview,
        modules=[module],
        phases=[phase],
        guides=[],
        resume_module_id="module-2",
        resume_phase_id="phase-2",
    )


def test_runtime_initialization_and_entrypoint_builds_objects() -> None:
    overview = make_overview()
    result = run_experiment_runtime(
        overview_factory=lambda _: overview,
        services=RuntimeServices(resolve_module=lambda _: ModuleResolution(kind=ModuleResolutionKind.PAUSE_MODULE)),
    )
    state = result.state
    assert state.current_overview_version == overview.version
    assert state.modules and state.phases
    assert state.current_module_id is None
    assert state.current_phase_id is None
    assert state.current_guide_id is None
    assert state.current_action_id is None
    assert state.runtime_status == RuntimeStatus.PAUSED


def test_initialized_state_defaults() -> None:
    overview = make_overview()
    state = initialize_runtime_state(overview=overview, modules=[make_module()], phases=[make_phase()])
    assert state.current_overview_version == overview.version
    assert state.current_module_id is None
    assert state.current_phase_id is None
    assert state.current_guide_id is None
    assert state.current_action_id is None
    assert state.runtime_status == RuntimeStatus.IN_PROGRESS


def test_terminal_state_handling() -> None:
    assert not is_terminal_status(RuntimeStatus.IN_PROGRESS)
    for status in [RuntimeStatus.COMPLETED, RuntimeStatus.PAUSED, RuntimeStatus.ESCALATED]:
        state = make_state()
        state.runtime_status = status
        result = run_runtime(state=state)
        assert result.kind == status.value


def test_invalid_overview_triggers_migration_and_auto_resume_updates_pointers() -> None:
    state = make_state()
    state.modules[0].overview_version = 2
    result = run_runtime(
        state=state,
        services=RuntimeServices(run_migration=lambda _: auto_migration_state()),
        max_iterations=1,
    )
    assert result.state.overview.version == 2
    assert result.state.current_overview_version == 2
    assert result.state.current_module_id == "module-2"
    assert result.state.current_phase_id == "phase-2"
    assert result.state.current_guide_id is None
    assert result.state.current_action_id is None


def test_migration_pause_and_escalate_set_terminal_status() -> None:
    for kind, status in [
        (RuntimeMigrationKind.PAUSE_MIGRATION, RuntimeStatus.PAUSED),
        (RuntimeMigrationKind.ESCALATE_MIGRATION, RuntimeStatus.ESCALATED),
    ]:
        state = make_state()
        state.overview.superseded_by_version = 2
        result = run_runtime(
            state=state,
            services=RuntimeServices(run_migration=lambda _: RuntimeMigrationResult(kind=kind)),
        )
        assert result.state.runtime_status == status


def test_module_resolution_handlers_and_migration_resume() -> None:
    state = make_state()
    assert handle_module_result(state, ModuleResolution(kind=ModuleResolutionKind.KEEP_CURRENT_MODULE)) == "continue_stages"
    assert state.current_module_id == "module-1"
    assert handle_module_result(state, ModuleResolution(kind=ModuleResolutionKind.SWITCH_MODULE, module_id="module-2")) == "continue_loop"
    assert state.current_module_id == "module-2"
    assert state.current_phase_id is None and state.current_guide_id is None and state.current_action_id is None
    assert handle_module_result(state, ModuleResolution(kind=ModuleResolutionKind.PAUSE_MODULE)) == "terminal"
    assert state.runtime_status == RuntimeStatus.PAUSED

    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            resolve_module=lambda _: ModuleResolution(kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: auto_migration_state(),
        ),
        max_iterations=1,
    )
    assert result.state.current_module_id == "module-2"


def test_phase_resolution_handlers_and_migration_resume() -> None:
    state = make_state()
    assert handle_phase_result(state, PhaseResolution(kind=PhaseResolutionKind.KEEP_CURRENT_PHASE)) == "continue_stages"
    assert handle_phase_result(state, PhaseResolution(kind=PhaseResolutionKind.SWITCH_PHASE, phase_id="phase-2")) == "continue_loop"
    assert state.current_phase_id == "phase-2"
    assert state.current_guide_id is None and state.current_action_id is None
    for kind in [
        PhaseResolutionKind.PAUSE_WAIT_EXTERNAL_TOOL_RESULT,
        PhaseResolutionKind.PAUSE_WAIT_HUMAN_INPUT,
        PhaseResolutionKind.PAUSE_WAIT_EXTERNAL_RESOURCE,
    ]:
        state = make_state()
        assert handle_phase_result(state, PhaseResolution(kind=kind)) == "terminal"
        assert state.runtime_status == RuntimeStatus.PAUSED
    state = make_state()
    assert handle_phase_result(state, PhaseResolution(kind=PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE)) == "continue_loop"
    assert state.current_guide_id is None and state.current_action_id is None

    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            resolve_phase=lambda _: PhaseResolution(kind=PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: auto_migration_state(),
        ),
        max_iterations=1,
    )
    assert result.state.current_phase_id == "phase-2"


def test_guide_resolution_handlers_and_migration_resume() -> None:
    state = make_state()
    state.current_guide_id = None
    assert handle_guide_result(state, GuideResolution(kind=GuideResolutionKind.USE_GUIDE, guide_id="guide-1")) == "continue_stages"
    assert state.current_guide_id == "guide-1"
    assert handle_guide_result(state, GuideResolution(kind=GuideResolutionKind.REVISE_GUIDE_KEEP_PHASE)) == "continue_loop"
    assert state.current_guide_id is None and state.current_action_id is None

    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            resolve_guide=lambda _: GuideResolution(kind=GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: auto_migration_state(),
        ),
        max_iterations=1,
    )
    assert result.state.current_guide_id is None and result.state.current_action_id is None


def test_missing_bound_guide_enters_migration_instead_of_crashing() -> None:
    trace: list[str] = []
    state = make_state()
    state.guides = []
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            trace=trace.append,
            resolve_guide=lambda _: GuideResolution(kind=GuideResolutionKind.USE_GUIDE, guide_id="missing-guide"),
            run_migration=lambda _: RuntimeMigrationResult(kind=RuntimeMigrationKind.ESCALATE_MIGRATION),
        ),
    )
    assert result.kind == "escalated"
    assert "overview_revision_migration" in trace
    assert "action_resolution" not in trace
    assert "current_guide_not_uniquely_bound" in result.state.issue_evidence


def test_ambiguous_bound_guide_enters_migration_instead_of_action_resolution() -> None:
    trace: list[str] = []
    state = make_state()

    def duplicate_guide(_scheduler_state):
        state.guides.append(make_guide("guide-1", actions=[make_action("action-2")]))
        return GuideResolution(kind=GuideResolutionKind.USE_GUIDE, guide_id="guide-1")

    result = run_runtime(
        state=state,
        services=RuntimeServices(
            trace=trace.append,
            resolve_guide=duplicate_guide,
            run_migration=lambda _: RuntimeMigrationResult(kind=RuntimeMigrationKind.ESCALATE_MIGRATION),
        ),
    )
    assert result.kind == "escalated"
    assert "overview_revision_migration" in trace
    assert "action_resolution" not in trace
    assert "current_guide_not_uniquely_bound" in result.state.issue_evidence


def test_action_resolution_handlers() -> None:
    for kind in [ActionResolutionKind.CONTINUE_CURRENT_ACTION, ActionResolutionKind.RETRY_CURRENT_ACTION]:
        state = make_state()
        assert handle_action_result(state, ActionResolution(kind=kind, action_id="action-1")) == "execute"
        assert state.current_action_id == "action-1"
    state = make_state()
    assert handle_action_result(
        state,
        ActionResolution(kind=ActionResolutionKind.ABANDON_CURRENT_ACTION_AND_SWITCH, action_id="action-2"),
    ) == "execute"
    assert state.current_action_id == "action-2"
    for kind in [
        ActionResolutionKind.PAUSE_WAIT_EXTERNAL_TOOL_RESULT,
        ActionResolutionKind.PAUSE_WAIT_HUMAN_INPUT,
        ActionResolutionKind.PAUSE_WAIT_EXTERNAL_RESOURCE,
        ActionResolutionKind.NO_EXECUTABLE_ACTION_PAUSE,
    ]:
        state = make_state()
        assert handle_action_result(state, ActionResolution(kind=kind)) == "terminal"
        assert state.runtime_status == RuntimeStatus.PAUSED
        assert state.waiting_context is not None
    for kind in [ActionResolutionKind.REVISE_GUIDE_KEEP_PHASE, ActionResolutionKind.NO_EXECUTABLE_ACTION_REVISE_GUIDE]:
        state = make_state()
        assert handle_action_result(state, ActionResolution(kind=kind)) == "continue_loop"
        assert state.current_guide_id is None and state.current_action_id is None


def test_action_escalation_enters_migration_subflow() -> None:
    for kind in [ActionResolutionKind.ESCALATE_TO_OVERVIEW_REVISION, ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE]:
        state = make_state()
        result = run_runtime(
            state=state,
            services=RuntimeServices(
                resolve_action=lambda _state, _guide, kind=kind: ActionResolution(kind=kind),
                run_migration=lambda _: auto_migration_state(),
            ),
            max_iterations=1,
        )
        assert result.state.current_action_id is None
        assert result.state.current_overview_version == 2


def test_acceptance_integration_routes() -> None:
    for kind, status in [("pause_acceptance", RuntimeStatus.PAUSED), ("experiment_done", RuntimeStatus.COMPLETED)]:
        state = make_state()
        assert handle_acceptance_result(state, AcceptanceEvaluationResult(kind=kind)) == "terminal"
        assert state.runtime_status == status
    for kind in ["keep_current_state", "phase_done", "module_done", "adopted"]:
        state = make_state()
        assert handle_acceptance_result(state, AcceptanceEvaluationResult(kind=kind)) == "continue_loop"
        assert state.runtime_status == RuntimeStatus.IN_PROGRESS
    state = make_state()
    assert handle_acceptance_result(state, AcceptanceEvaluationResult(kind="revise_guide")) == "continue_loop"
    assert state.current_guide_id is None and state.current_action_id is None

    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            evaluate_acceptance=lambda _: [AcceptanceEvaluationResult(kind="escalate_to_overview_revision")],
            run_migration=lambda _: auto_migration_state(),
        ),
        max_iterations=1,
    )
    assert result.state.current_overview_version == 2


def test_adopted_acceptance_result_is_persisted_and_loop_continues() -> None:
    adopted = make_adopted_item()
    result = run_runtime(
        state=make_state(),
        services=RuntimeServices(
            resolve_action=lambda _state, _guide: ActionResolution(kind=ActionResolutionKind.CONTINUE_CURRENT_ACTION, action_id="action-1"),
            execute_action=lambda _: ExecutionWritebackResult(),
            evaluate_acceptance=lambda _: [
                AcceptanceEvaluationResult(kind="adopted", adopted_item=adopted),
                AcceptanceEvaluationResult(kind="experiment_done"),
            ],
        ),
    )
    assert result.kind == "completed"
    assert result.state.adopted_results == [adopted]


def test_non_adopted_acceptance_result_does_not_append_adopted_result() -> None:
    state = make_state()
    assert handle_acceptance_result(state, AcceptanceEvaluationResult(kind="keep_current_state")) == "continue_loop"
    assert state.adopted_results == []

    state = make_state()
    assert handle_acceptance_result(state, AcceptanceEvaluationResult(kind="adopted")) == "continue_loop"
    assert state.adopted_results == []


def test_loop_order_and_early_failure_prevents_later_stages() -> None:
    trace: list[str] = []
    state = make_state()
    run_runtime(
        state=state,
        services=RuntimeServices(
            trace=trace.append,
            resolve_action=lambda _state, _guide: ActionResolution(kind=ActionResolutionKind.CONTINUE_CURRENT_ACTION, action_id="action-1"),
            execute_action=lambda _: ExecutionWritebackResult(),
            evaluate_acceptance=lambda _: [AcceptanceEvaluationResult(kind="experiment_done")],
        ),
    )
    assert trace == [
        "terminal_check",
        "overview_validity",
        "module_resolution",
        "phase_resolution",
        "guide_resolution",
        "action_resolution",
        "execution_writeback",
        "acceptance_promotion",
        "terminal_recheck",
    ]

    trace = []
    state = make_state()
    run_runtime(
        state=state,
        services=RuntimeServices(
            trace=trace.append,
            resolve_phase=lambda _: PhaseResolution(kind=PhaseResolutionKind.PAUSE_WAIT_HUMAN_INPUT),
        ),
    )
    assert "guide_resolution" not in trace
    assert "action_resolution" not in trace


def test_pause_preserves_context_and_no_silent_reset() -> None:
    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(resolve_action=lambda _state, _guide: ActionResolution(kind=ActionResolutionKind.PAUSE_WAIT_HUMAN_INPUT)),
    )
    assert result.state.runtime_status == RuntimeStatus.PAUSED
    assert result.state.current_overview_version == 1
    assert result.state.current_module_id == "module-1"
    assert result.state.current_phase_id == "phase-1"
    assert result.state.current_guide_id == "guide-1"
    assert result.state.current_action_id == "action-1"
    assert result.state.waiting_context == {"origin": "pause_wait_human_input", "action_id": "action-1"}


def test_escalated_runtime_stops_and_migration_escalation_does_not_continue() -> None:
    trace: list[str] = []
    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            trace=trace.append,
            resolve_module=lambda _: ModuleResolution(kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: RuntimeMigrationResult(kind=RuntimeMigrationKind.ESCALATE_MIGRATION),
        ),
    )
    assert result.kind == "escalated"
    assert "phase_resolution" not in trace


def test_migration_reentry_safety_rules() -> None:
    trace: list[str] = []
    state = make_state()
    old_overview_dump = state.overview.model_dump()
    old_guide_id = state.current_guide_id
    state.current_action_id = "old-action"
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            trace=trace.append,
            resolve_module=lambda _: ModuleResolution(kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: auto_migration_state(),
        ),
        max_iterations=2,
    )
    assert trace.count("module_resolution") == 2
    assert result.state.current_action_id is None
    assert result.state.current_guide_id is None
    assert old_guides_inactive_after_migration(result.state, {old_guide_id})
    assert old_overview_dump["superseded_by_version"] is None


def test_missing_unique_resume_point_escalates_instead_of_guessing() -> None:
    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(
            resolve_module=lambda _: ModuleResolution(kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: RuntimeMigrationResult(kind=RuntimeMigrationKind.AUTO_RESUMED, overview=make_overview(version=2)),
        ),
    )
    assert result.kind == "escalated"
    assert "migration_missing_unique_resume_point" in result.state.issue_evidence


def test_runtime_loop_iteration_limit_is_explicit_safety_result() -> None:
    state = make_state()
    result = run_runtime(
        state=state,
        services=RuntimeServices(evaluate_acceptance=lambda _: [AcceptanceEvaluationResult(kind="keep_current_state")]),
        max_iterations=1,
    )
    assert result.kind == "escalated"
    assert result.reason == "runtime_iteration_limit_exceeded"


def test_minimal_end_to_end_completed_paused_auto_resume_and_migration_failure() -> None:
    completed = run_runtime(
        state=make_state(),
        services=RuntimeServices(
            resolve_action=lambda _state, _guide: ActionResolution(kind=ActionResolutionKind.CONTINUE_CURRENT_ACTION, action_id="action-1"),
            execute_action=lambda _: ExecutionWritebackResult(),
            evaluate_acceptance=lambda _: [AcceptanceEvaluationResult(kind="experiment_done")],
        ),
    )
    assert completed.kind == "completed"

    paused = run_runtime(
        state=make_state(),
        services=RuntimeServices(resolve_action=lambda _state, _guide: ActionResolution(kind=ActionResolutionKind.NO_EXECUTABLE_ACTION_PAUSE)),
    )
    assert paused.kind == "paused"

    resumed = run_runtime(
        state=make_state(),
        services=RuntimeServices(
            resolve_guide=lambda _: GuideResolution(kind=GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: auto_migration_state(),
        ),
        max_iterations=1,
    )
    assert resumed.state.current_overview_version == 2

    failed = run_runtime(
        state=make_state(),
        services=RuntimeServices(
            resolve_guide=lambda _: GuideResolution(kind=GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION),
            run_migration=lambda _: RuntimeMigrationResult(kind=RuntimeMigrationKind.ESCALATE_MIGRATION),
        ),
    )
    assert failed.kind == "escalated"
