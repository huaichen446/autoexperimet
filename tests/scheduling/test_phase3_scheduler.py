from __future__ import annotations

from agent_runtime.execution import block_attempt, create_attempt, fail_attempt, finalize_attempt, start_running
from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionType,
    BlockedReason,
    DecisionItem,
    DoneCheck,
    ExecutionGuide,
    ExperimentOverview,
    FailureReason,
    GuideStatus,
    Module,
    ModuleOverview,
    ModuleStatus,
    ObjectInventory,
    Phase,
    PhaseOverview,
    PhaseStatus,
    WaitingTarget,
)
from agent_runtime.scheduling import (
    ActionResolutionKind,
    GuideResolutionKind,
    ModuleResolutionKind,
    PhaseResolutionKind,
    SchedulerRuntimeState,
    classify_blocked_action,
    resolve_current_action,
    resolve_current_active_guide,
    schedule_runtime,
    select_action_from_guide,
    validate_current_module,
    validate_current_phase,
)


def build_state(
    *,
    current_module_id: str | None = "module-1",
    current_phase_id: str | None = "phase-1",
    current_action_id: str | None = None,
    module_overrides: dict[str, dict] | None = None,
    phase_overrides: dict[str, dict] | None = None,
    guide_overrides: dict[str, dict] | None = None,
    action_overrides: dict[str, dict] | None = None,
    satisfied_state_afters: set[str] | None = None,
    locally_repairable_phase_ids: set[str] | None = None,
    useful_returned_action_ids: set[str] | None = None,
    guides: list[ExecutionGuide] | None = None,
    action_records: list = None,
) -> SchedulerRuntimeState:
    overview = build_overview()
    modules = [
        build_module("module-1", "module-ov-1", "Discovery", ModuleStatus.IN_PROGRESS, ["phase-1", "phase-2"]),
        build_module("module-2", "module-ov-2", "Delivery", ModuleStatus.NOT_STARTED, ["phase-3"]),
    ]
    phases = [
        build_phase("phase-1", "module-1", "phase-ov-1", "signals gathered", PhaseStatus.IN_PROGRESS),
        build_phase("phase-2", "module-1", "phase-ov-2", "synthesis complete", PhaseStatus.NOT_STARTED),
        build_phase("phase-3", "module-2", "phase-ov-3", "delivery ready", PhaseStatus.NOT_STARTED),
    ]
    actions = [
        build_action("action-1", decision_refs=["decision-1"], done_refs=["check-1"], priority=5, declared_order=0),
        build_action("action-2", decision_refs=["decision-1"], done_refs=[], priority=2, declared_order=1),
    ]
    guides = [build_guide(actions=actions)] if guides is None else guides

    for module in modules:
        if module_overrides and module.module_id in module_overrides:
            apply_model_override(module, module_overrides[module.module_id])
    for phase in phases:
        if phase_overrides and phase.phase_id in phase_overrides:
            apply_model_override(phase, phase_overrides[phase.phase_id])
    for guide in guides:
        if guide_overrides and guide.guide_id in guide_overrides:
            apply_model_override(guide, guide_overrides[guide.guide_id])
        for action in guide.actions:
            if action_overrides and action.action_id in action_overrides:
                apply_model_override(action, action_overrides[action.action_id])

    inventory = ObjectInventory(
        experiment_overview=overview,
        modules=modules,
        phases=phases,
        guides=guides,
        action_records=action_records or [],
        main_doc=None,
    )
    return SchedulerRuntimeState(
        inventory=inventory,
        current_module_id=current_module_id,
        current_phase_id=current_phase_id,
        current_action_id=current_action_id,
        satisfied_state_afters=satisfied_state_afters or set(),
        locally_repairable_phase_ids=locally_repairable_phase_ids or set(),
        useful_returned_action_ids=useful_returned_action_ids or set(),
    )


def build_overview() -> ExperimentOverview:
    module_1_phases = [
        PhaseOverview(
            phase_overview_id="phase-ov-1",
            module_overview_id="module-ov-1",
            experiment_id="exp-1",
            overview_version=1,
            name="Investigate",
            role="collect",
            state_after="signals gathered",
            why_phase_not_action="Need multiple actions.",
            transition_to_next="Move to synthesis.",
            sort_index=0,
        ),
        PhaseOverview(
            phase_overview_id="phase-ov-2",
            module_overview_id="module-ov-1",
            experiment_id="exp-1",
            overview_version=1,
            name="Synthesize",
            role="synthesize",
            state_after="synthesis complete",
            why_phase_not_action="Need round-level control.",
            transition_to_next="Move to delivery.",
            sort_index=1,
        ),
    ]
    module_2_phases = [
        PhaseOverview(
            phase_overview_id="phase-ov-3",
            module_overview_id="module-ov-2",
            experiment_id="exp-1",
            overview_version=1,
            name="Deliver",
            role="deliver",
            state_after="delivery ready",
            why_phase_not_action="Need multiple candidate actions.",
            transition_to_next="Done.",
            sort_index=0,
        )
    ]
    return ExperimentOverview(
        overview_id="overview-1",
        experiment_id="exp-1",
        version=1,
        parent_version=None,
        experiment_title="Phase 3 runtime scheduling",
        experiment_description="Scheduler coverage.",
        experiment_environment="local",
        experiment_objective="Resolve current execution point.",
        module_decomposition_feasibility="multi_module",
        module_decomposition_rationale=["Two modules are enough for selection tests."],
        modules=[
            ModuleOverview(
                module_overview_id="module-ov-1",
                experiment_id="exp-1",
                overview_version=1,
                name="Discovery",
                goal="Understand the problem.",
                why_independent="Produces inputs for later work.",
                inputs=[],
                outputs=["signals"],
                contribution_to_experiment="Finds the shape of the work.",
                phase_overviews=module_1_phases,
                phase_convergence_note="Enough evidence exists.",
                depends_on_module_names=[],
                sort_index=0,
            ),
            ModuleOverview(
                module_overview_id="module-ov-2",
                experiment_id="exp-1",
                overview_version=1,
                name="Delivery",
                goal="Deliver the result.",
                why_independent="Depends on discovery only.",
                inputs=["signals"],
                outputs=["delivery"],
                contribution_to_experiment="Finalizes the outcome.",
                phase_overviews=module_2_phases,
                phase_convergence_note="Delivery artifact exists.",
                depends_on_module_names=["Discovery"],
                sort_index=1,
            ),
        ],
        experiment_convergence_note="Scheduler can pick one next step.",
        failure_localization_note="Failures should stay at the narrowest layer.",
        audit_status="passed",
        audit_issue_summary=[],
        audit_passed_at="2026-04-22T10:00:00Z",
        change_summary="Phase 3 scheduling.",
        created_at="2026-04-22T09:00:00Z",
        superseded_by_version=None,
    )


def build_module(module_id: str, overview_ref: str, name: str, status: ModuleStatus, phase_ids: list[str]) -> Module:
    return Module(
        module_id=module_id,
        experiment_id="exp-1",
        overview_version=1,
        module_overview_ref=overview_ref,
        name=name,
        goal=f"{name} goal",
        phase_ids=phase_ids,
        current_phase_id=phase_ids[0],
        completed_phase_ids=[],
        blocked_phase_ids=[],
        status=status,
        notes=[],
        failure_reasons=[],
        retry_history=[],
        needs_redecomposition=False,
        created_at="2026-04-22T09:01:00Z",
        updated_at="2026-04-22T09:02:00Z",
    )


def build_phase(phase_id: str, module_id: str, overview_ref: str, state_after: str, status: PhaseStatus) -> Phase:
    return Phase(
        phase_id=phase_id,
        module_id=module_id,
        experiment_id="exp-1",
        overview_version=1,
        phase_overview_ref=overview_ref,
        name=phase_id,
        role="role",
        state_after=state_after,
        status=status,
        is_expanded=False,
        notes=[],
        failure_reasons=[],
        retry_history=[],
        fallback_boundary="Stay inside the phase.",
        created_at="2026-04-22T09:01:00Z",
        updated_at="2026-04-22T09:02:00Z",
    )


def build_action(
    action_id: str,
    *,
    action_type: ActionType = ActionType.AUTO,
    decision_refs: list[str],
    done_refs: list[str],
    priority: int,
    declared_order: int,
) -> Action:
    executor = {
        ActionType.AUTO: ActionExecutorHint.AGENT,
        ActionType.EXTERNAL_TOOL: ActionExecutorHint.TOOL,
        ActionType.HUMAN_INPUT: ActionExecutorHint.HUMAN,
    }[action_type]
    return Action(
        action_id=action_id,
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        overview_version=1,
        title=action_id,
        action_type=action_type,
        executor_type=executor,
        instruction="Do work.",
        expected_output="Output.",
        required_inputs=[],
        decision_item_refs=decision_refs,
        done_check_refs=done_refs,
        expected_output_refs=[],
        retry_policy="fixed",
        max_retry=2,
        priority=priority,
        declared_order=declared_order,
    )


def build_guide(*, guide_id: str = "guide-1", guide_version: int = 1, created_at: str = "2026-04-22T09:05:00Z", actions: list[Action]) -> ExecutionGuide:
    return ExecutionGuide(
        guide_id=guide_id,
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        overview_version=1,
        guide_version=guide_version,
        status=GuideStatus.ACTIVE,
        phase_problem="Need the next runtime action.",
        decision_items=[
            DecisionItem(
                decision_id="decision-1",
                experiment_id="exp-1",
                module_id="module-1",
                phase_id="phase-1",
                guide_id=guide_id,
                overview_version=1,
                title="Which path?",
                decision_scope="phase",
                decision_type="path_selection",
                status="open",
                required_for_phase_done=True,
                created_at="2026-04-22T09:05:00Z",
                updated_at="2026-04-22T09:05:00Z",
            )
        ],
        actions=actions,
        done_criteria=[
            DoneCheck(
                check_id="check-1",
                experiment_id="exp-1",
                module_id="module-1",
                phase_id="phase-1",
                guide_id=guide_id,
                overview_version=1,
                check_scope="phase",
                title="Evidence exists.",
                check_type="evidence_bound",
                status="unmet",
                required=True,
                verifier_type="evidence_based",
                verifier_config={"source": "guide"},
                created_at="2026-04-22T09:05:00Z",
                updated_at="2026-04-22T09:05:00Z",
            )
        ],
        blockers=[],
        fallback_rule="Stay inside the phase boundary.",
        notes=[],
        created_from_phase_ref="phase-1",
        created_at=created_at,
        superseded_by=None,
    )


def apply_model_override(model, updates: dict) -> None:
    for field_name, value in updates.items():
        setattr(model, field_name, value)


def build_blocked_reason(reason_type: str) -> BlockedReason:
    return BlockedReason(
        blocked_reason_type=reason_type,
        code=reason_type,
        message=reason_type,
        retryable_after_unblock=True,
    )


def build_failure_reason(*, code: str = "temporary", retryable: bool = True, counts_as_retry: bool = True) -> FailureReason:
    return FailureReason(
        category="transient_failure" if retryable else "dependency_missing",
        code=code,
        message=code,
        retryable=retryable,
        counts_as_retry=counts_as_retry,
    )


def attach_blocked_record(state: SchedulerRuntimeState, action_id: str, reason_type: str) -> None:
    action = next(action for action in state.inventory.guides[0].actions if action.action_id == action_id)
    record = create_attempt(action, state.inventory.action_records, action_record_id=f"record-{action_id}", created_at="2026-04-22T11:00:00Z")
    start_running(record, started_at="2026-04-22T11:01:00Z")
    waiting_target = None
    if reason_type in {"external_tool_not_ready", "human_input_missing", "external_resource_not_ready"}:
        waiting_type = {
            "external_tool_not_ready": "external_tool",
            "human_input_missing": "human",
            "external_resource_not_ready": "external_resource",
        }[reason_type]
        waiting_target = WaitingTarget(waiting_type=waiting_type, target_id="target", correlation_key="corr-1")
    block_attempt(record, build_blocked_reason(reason_type), waiting_target=waiting_target)


def attach_failed_record(
    state: SchedulerRuntimeState,
    action_id: str,
    *,
    retryable: bool = True,
    counts_as_retry: bool = True,
) -> None:
    action = next(action for action in state.inventory.guides[0].actions if action.action_id == action_id)
    record = create_attempt(action, state.inventory.action_records, action_record_id=f"record-{action_id}", created_at="2026-04-22T11:00:00Z")
    start_running(record, started_at="2026-04-22T11:01:00Z")
    fail_attempt(
        record,
        build_failure_reason(retryable=retryable, counts_as_retry=counts_as_retry),
        terminal_at="2026-04-22T11:02:00Z",
    )
    finalize_attempt(record, finalized_at="2026-04-22T11:03:00Z")


def test_module_validation_and_selection_outcomes() -> None:
    state = build_state()
    state.inventory.modules[0].overview_version = 2
    assert validate_current_module(state).kind == ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION

    state = build_state(
        module_overrides={"module-1": {"status": ModuleStatus.DONE}, "module-2": {"status": ModuleStatus.NOT_STARTED}},
        phase_overrides={"phase-3": {"status": PhaseStatus.NOT_STARTED}},
    )
    assert validate_current_module(state).kind == ModuleResolutionKind.SWITCH_MODULE
    assert validate_current_module(state).module_id == "module-2"

    state = build_state(module_overrides={"module-1": {"status": ModuleStatus.BLOCKED, "blocked_phase_ids": ["phase-1"]}})
    state.inventory.experiment_overview.modules[1].depends_on_module_names = []
    assert validate_current_module(state).kind == ModuleResolutionKind.SWITCH_MODULE

    state = build_state(
        module_overrides={
            "module-1": {"status": ModuleStatus.BLOCKED, "blocked_phase_ids": ["phase-1"]},
            "module-2": {"status": ModuleStatus.BLOCKED, "blocked_phase_ids": ["phase-3"]},
        },
        phase_overrides={
            "phase-1": {"status": PhaseStatus.BLOCKED, "failure_reasons": ["external_tool_not_ready"]},
            "phase-3": {"status": PhaseStatus.BLOCKED, "failure_reasons": ["human_input_missing"]},
        },
    )
    assert validate_current_module(state).kind == ModuleResolutionKind.PAUSE_MODULE

    state = build_state(module_overrides={"module-1": {"status": ModuleStatus.FAILED, "failure_reasons": ["skeleton_inconsistency"]}})
    assert validate_current_module(state).kind == ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION

    state = build_state(
        module_overrides={
            "module-1": {"status": ModuleStatus.BLOCKED, "blocked_phase_ids": ["phase-1"]},
            "module-2": {"status": ModuleStatus.BLOCKED, "blocked_phase_ids": ["phase-3"]},
        },
        phase_overrides={
            "phase-1": {"status": PhaseStatus.BLOCKED, "failure_reasons": ["guide_missing_info"]},
            "phase-3": {"status": PhaseStatus.BLOCKED, "failure_reasons": ["guide_missing_info"]},
        },
    )
    assert validate_current_module(state).kind != ModuleResolutionKind.PAUSE_MODULE


def test_phase_validation_and_selection_outcomes() -> None:
    state = build_state()
    state.inventory.phases[0].overview_version = 2
    assert validate_current_phase(state).kind == PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION

    state = build_state(
        phase_overrides={"phase-1": {"status": PhaseStatus.DONE}},
        satisfied_state_afters={"signals gathered"},
    )
    phase_result = validate_current_phase(state)
    assert phase_result.kind == PhaseResolutionKind.SWITCH_PHASE
    assert phase_result.phase_id == "phase-2"

    state = build_state(phase_overrides={"phase-1": {"status": PhaseStatus.DONE}})
    assert validate_current_phase(state).kind == PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE

    state = build_state(phase_overrides={"phase-1": {"status": PhaseStatus.BLOCKED, "failure_reasons": ["external_tool_not_ready"]}})
    assert validate_current_phase(state).kind == PhaseResolutionKind.PAUSE_WAIT_EXTERNAL_TOOL_RESULT

    state = build_state(phase_overrides={"phase-1": {"status": PhaseStatus.BLOCKED, "failure_reasons": ["guide_missing_info"]}})
    assert validate_current_phase(state).kind == PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE

    state = build_state(phase_overrides={"phase-1": {"status": PhaseStatus.FAILED, "failure_reasons": ["recoverable_failure"]}})
    assert validate_current_phase(state).kind == PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE

    state = build_state(phase_overrides={"phase-1": {"status": PhaseStatus.FAILED, "failure_reasons": ["undeclared_dependency"]}})
    assert validate_current_phase(state).kind == PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION

    state = build_state(phase_overrides={"phase-1": {"status": PhaseStatus.FAILED, "failure_reasons": ["fallback_boundary_violation"]}})
    assert validate_current_phase(state).kind == PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION


def test_guide_resolution_tie_breakers_and_missing_guide_routing() -> None:
    guides = [
        build_guide(guide_id="guide-z", guide_version=1, created_at="2026-04-22T09:06:00Z", actions=[build_action("guide-z-action", decision_refs=["decision-1"], done_refs=["check-1"], priority=1, declared_order=0)]),
        build_guide(guide_id="guide-b", guide_version=2, created_at="2026-04-22T09:05:00Z", actions=[build_action("guide-b-action", decision_refs=["decision-1"], done_refs=["check-1"], priority=1, declared_order=0)]),
        build_guide(guide_id="guide-a", guide_version=2, created_at="2026-04-22T09:05:00Z", actions=[build_action("guide-a-action", decision_refs=["decision-1"], done_refs=["check-1"], priority=1, declared_order=0)]),
        build_guide(guide_id="guide-c", guide_version=2, created_at="2026-04-22T09:07:00Z", actions=[build_action("guide-c-action", decision_refs=["decision-1"], done_refs=["check-1"], priority=1, declared_order=0)]),
    ]
    state = build_state(guides=guides)
    result = resolve_current_active_guide(state)
    assert result.kind == GuideResolutionKind.USE_GUIDE
    assert result.guide_id == "guide-c"

    state = build_state(guides=[], locally_repairable_phase_ids={"phase-1"})
    assert resolve_current_active_guide(state).kind == GuideResolutionKind.REVISE_GUIDE_KEEP_PHASE

    state = build_state(guides=[])
    assert resolve_current_active_guide(state).kind == GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION


def test_action_blocked_classification_routes() -> None:
    for reason_type, expected in [
        ("external_tool_not_ready", ActionResolutionKind.PAUSE_WAIT_EXTERNAL_TOOL_RESULT),
        ("human_input_missing", ActionResolutionKind.PAUSE_WAIT_HUMAN_INPUT),
        ("external_resource_not_ready", ActionResolutionKind.PAUSE_WAIT_EXTERNAL_RESOURCE),
        ("guide_missing_info", ActionResolutionKind.REVISE_GUIDE_KEEP_PHASE),
        ("undeclared_dependency", ActionResolutionKind.ESCALATE_TO_OVERVIEW_REVISION),
        ("fallback_boundary_violation", ActionResolutionKind.ESCALATE_TO_OVERVIEW_REVISION),
    ]:
        state = build_state(current_action_id="action-1")
        attach_blocked_record(state, "action-1", reason_type)
        guide = state.inventory.guides[0]
        assert classify_blocked_action(guide.actions[0], state) == reason_type
        assert resolve_current_action(state, guide).kind == expected


def test_action_continue_retry_abandon_and_no_executable_routes() -> None:
    state = build_state(current_action_id="action-1")
    record = create_attempt(state.inventory.guides[0].actions[0], state.inventory.action_records, action_record_id="record-1", created_at="2026-04-22T11:00:00Z")
    start_running(record, started_at="2026-04-22T11:01:00Z")
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.CONTINUE_CURRENT_ACTION

    state = build_state(current_action_id="action-1")
    attach_failed_record(state, "action-1")
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.RETRY_CURRENT_ACTION

    state = build_state(current_action_id="action-1")
    attach_failed_record(state, "action-1", retryable=False, counts_as_retry=False)
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.ABANDON_CURRENT_ACTION_AND_SWITCH

    state = build_state(current_action_id="action-1")
    attach_failed_record(state, "action-1", retryable=False, counts_as_retry=False)
    guide = state.inventory.guides[0]
    result = resolve_current_action(state, guide)
    assert result.kind == ActionResolutionKind.ABANDON_CURRENT_ACTION_AND_SWITCH
    assert result.action_id == "action-2"

    state = build_state(current_action_id="action-2")
    attach_blocked_record(state, "action-1", "external_tool_not_ready")
    attach_failed_record(state, "action-2", retryable=False, counts_as_retry=False)
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.NO_EXECUTABLE_ACTION_PAUSE

    state = build_state(locally_repairable_phase_ids={"phase-1"})
    attach_failed_record(state, "action-1", retryable=False, counts_as_retry=False)
    attach_failed_record(state, "action-2", retryable=False, counts_as_retry=False)
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.NO_EXECUTABLE_ACTION_REVISE_GUIDE

    state = build_state()
    bad_guide = state.inventory.guides[0].model_copy(update={"phase_id": "phase-2"})
    assert resolve_current_action(state, bad_guide).kind == ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE


def test_multiple_waiting_actions_bind_pause_to_one_unique_action() -> None:
    actions = [
        build_action("action-c", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=2),
        build_action("action-b", decision_refs=["decision-1"], done_refs=[], priority=5, declared_order=1),
        build_action("action-a", decision_refs=["decision-1"], done_refs=[], priority=5, declared_order=1),
    ]
    guide = build_guide(actions=actions)
    state = build_state(guides=[guide], current_action_id="action-c")
    attach_blocked_record(state, "action-a", "human_input_missing")
    attach_blocked_record(state, "action-b", "external_tool_not_ready")
    attach_failed_record(state, "action-c", retryable=False, counts_as_retry=False)

    result = resolve_current_action(state, guide)
    assert result.kind == ActionResolutionKind.NO_EXECUTABLE_ACTION_PAUSE
    assert result.action_id == "action-a"


def test_all_guide_actions_support_nothing_escalates() -> None:
    actions = [
        build_action("action-1", decision_refs=[], done_refs=[], priority=5, declared_order=0),
        build_action("action-2", decision_refs=[], done_refs=[], priority=1, declared_order=1),
    ]
    guide = build_guide(actions=actions)
    state = build_state(guides=[guide])

    result = resolve_current_action(state, guide)
    assert result.kind == ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE


def test_action_selection_tie_breakers() -> None:
    actions = [
        build_action("action-a", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=1),
        build_action("action-b", decision_refs=["decision-1", "decision-2"], done_refs=[], priority=1, declared_order=1),
    ]
    guide = build_guide(actions=actions)
    guide.decision_items.append(
        DecisionItem(
            decision_id="decision-2",
            experiment_id="exp-1",
            module_id="module-1",
            phase_id="phase-1",
            guide_id="guide-1",
            overview_version=1,
            title="Second?",
            decision_scope="phase",
            decision_type="path_selection",
            status="open",
            required_for_phase_done=True,
            created_at="2026-04-22T09:05:00Z",
            updated_at="2026-04-22T09:05:00Z",
        )
    )
    state = build_state(guides=[guide])
    assert select_action_from_guide(guide, state).action_id == "action-b"

    actions = [
        build_action("action-a", decision_refs=["decision-1"], done_refs=["check-1"], priority=1, declared_order=1),
        build_action("action-b", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=1),
    ]
    guide = build_guide(actions=actions)
    state = build_state(guides=[guide])
    assert select_action_from_guide(guide, state).action_id == "action-a"

    actions = [
        build_action("action-a", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=1),
        build_action("action-b", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=1),
    ]
    guide = build_guide(actions=actions)
    state = build_state(guides=[guide], current_action_id="action-b")
    record = create_attempt(guide.actions[1], state.inventory.action_records, action_record_id="record-1", created_at="2026-04-22T11:00:00Z")
    start_running(record, started_at="2026-04-22T11:01:00Z")
    assert select_action_from_guide(guide, state).action_id == "action-b"

    actions = [
        build_action("action-a", decision_refs=["decision-1"], done_refs=[], priority=5, declared_order=1),
        build_action("action-b", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=1),
    ]
    guide = build_guide(actions=actions)
    state = build_state(guides=[guide])
    assert select_action_from_guide(guide, state).action_id == "action-a"

    actions = [
        build_action("action-a", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=0),
        build_action("action-b", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=1),
    ]
    guide = build_guide(actions=actions)
    state = build_state(guides=[guide])
    assert select_action_from_guide(guide, state).action_id == "action-a"

    actions = [
        build_action("action-a", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=0),
        build_action("action-b", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=0),
    ]
    guide = build_guide(actions=actions)
    state = build_state(guides=[guide])
    assert select_action_from_guide(guide, state).action_id == "action-a"


def test_human_input_special_rules() -> None:
    actions = [
        build_action("action-1", action_type=ActionType.HUMAN_INPUT, decision_refs=["decision-1"], done_refs=["check-1"], priority=5, declared_order=0),
        build_action("action-2", decision_refs=["decision-1"], done_refs=[], priority=1, declared_order=1),
    ]
    guide = build_guide(actions=actions)

    state = build_state(guides=[guide], current_action_id="action-1")
    attach_failed_record(state, "action-1")
    assert resolve_current_action(state, guide).kind != ActionResolutionKind.RETRY_CURRENT_ACTION

    state = build_state(guides=[guide], current_action_id="action-1", useful_returned_action_ids={"action-1"})
    attach_blocked_record(state, "action-1", "human_input_missing")
    assert resolve_current_action(state, guide).kind == ActionResolutionKind.CONTINUE_CURRENT_ACTION

    invalid_state = build_state(guides=[], useful_returned_action_ids={"action-1"}, locally_repairable_phase_ids={"phase-1"})
    assert schedule_runtime(invalid_state).kind == GuideResolutionKind.REVISE_GUIDE_KEEP_PHASE

    invalid_state = build_state(guides=[], useful_returned_action_ids={"action-1"})
    assert schedule_runtime(invalid_state).kind == GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION


def test_conflict_priority_is_fixed() -> None:
    state = build_state()
    state.inventory.guides[0].blockers = ["guide_missing_info", "undeclared_dependency", "external_tool_not_ready"]
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.ESCALATE_TO_OVERVIEW_REVISION

    state = build_state()
    state.inventory.guides[0].blockers = ["external_tool_not_ready", "guide_missing_info"]
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.REVISE_GUIDE_KEEP_PHASE

    state = build_state(current_action_id="action-1")
    attach_blocked_record(state, "action-1", "external_tool_not_ready")
    assert resolve_current_action(state, state.inventory.guides[0]).kind == ActionResolutionKind.PAUSE_WAIT_EXTERNAL_TOOL_RESULT


def test_missing_result_safety_is_explicit() -> None:
    state = build_state(guides=[])
    state.inventory.modules[0].status = ModuleStatus.DONE
    state.inventory.modules[1].status = ModuleStatus.BLOCKED
    state.inventory.modules[1].blocked_phase_ids = ["phase-3"]
    state.inventory.phases[2].status = PhaseStatus.BLOCKED
    state.inventory.phases[2].failure_reasons = ["external_tool_not_ready"]
    result = schedule_runtime(state)
    assert result.kind == ModuleResolutionKind.PAUSE_MODULE

    state = build_state()
    state.inventory.guides[0].actions = []
    result = schedule_runtime(state)
    assert result.kind == ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE
