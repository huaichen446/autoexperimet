from __future__ import annotations

from pydantic import ValidationError
import pytest

from agent_runtime.execution import start_running
from agent_runtime.migration import (
    MigrationMappingType,
    MigrationOutcomeKind,
    MigrationStatus,
    ModuleMigrationItem,
    PhaseMigrationItem,
    StateInheritanceMode,
    build_modules_from_overview,
    build_phases_from_overview,
    freeze_old_active_runtime,
    handle_phase_mapping,
    has_complete_mapping,
    migrate_overview,
    relink_historical_action_records,
    resolve_resume_module,
    resolve_resume_phase,
)
from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionRecord,
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
    Phase,
    PhaseOverview,
    PhaseStatus,
    WaitingTarget,
)


def make_phase_overview(
    phase_id: str,
    module_id: str,
    *,
    version: int,
    role: str = "collect",
    state_after: str = "done",
    sort_index: int = 0,
) -> PhaseOverview:
    return PhaseOverview(
        phase_overview_id=phase_id,
        module_overview_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        name=phase_id,
        role=role,
        state_after=state_after,
        why_phase_not_action="Phase-level control",
        transition_to_next="next",
        sort_index=sort_index,
    )


def make_module_overview(
    module_id: str,
    phase_ids: list[str],
    *,
    version: int,
    role_prefix: str = "role",
    state_prefix: str = "state",
    sort_index: int = 0,
    depends_on: list[str] | None = None,
) -> ModuleOverview:
    return ModuleOverview(
        module_overview_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        name=module_id,
        goal=f"goal-{module_id}",
        why_independent="independent",
        inputs=[],
        outputs=[],
        contribution_to_experiment="contributes",
        phase_overviews=[
            make_phase_overview(
                phase_id,
                module_id,
                version=version,
                role=f"{role_prefix}-{phase_id}",
                state_after=f"{state_prefix}-{phase_id}",
                sort_index=index,
            )
            for index, phase_id in enumerate(phase_ids)
        ],
        phase_convergence_note="done",
        depends_on_module_names=[] if depends_on is None else depends_on,
        sort_index=sort_index,
    )


def make_overview(
    version: int,
    module_defs: list[tuple[str, list[str]]],
    *,
    parent_version: int | None = None,
    depends_on_by_module: dict[str, list[str]] | None = None,
) -> ExperimentOverview:
    return ExperimentOverview(
        overview_id=f"overview-{version}",
        experiment_id="exp-1",
        version=version,
        parent_version=parent_version,
        experiment_title="Phase 5",
        experiment_description="migration tests",
        experiment_environment="local",
        experiment_objective="migrate",
        module_decomposition_feasibility="multi_module",
        module_decomposition_rationale=["needed"],
        modules=[
            make_module_overview(
                module_id,
                phase_ids,
                version=version,
                sort_index=index,
                depends_on=(depends_on_by_module or {}).get(module_id, []),
            )
            for index, (module_id, phase_ids) in enumerate(module_defs)
        ],
        experiment_convergence_note="done",
        failure_localization_note="local",
        audit_status="passed",
        audit_issue_summary=[],
        audit_passed_at="2026-04-22T12:00:00Z",
        change_summary=f"overview-{version}",
        structural_change_summary=[],
        created_at=f"2026-04-22T12:0{version}:00Z",
        superseded_by_version=None,
    )


def make_module(module_id: str, phase_ids: list[str], *, version: int, status: ModuleStatus = ModuleStatus.IN_PROGRESS) -> Module:
    return Module(
        module_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        module_overview_ref=module_id,
        name=module_id,
        goal=f"goal-{module_id}",
        phase_ids=phase_ids,
        current_phase_id=phase_ids[0] if phase_ids else None,
        completed_phase_ids=[],
        blocked_phase_ids=[],
        status=status,
        notes=["note-1"],
        failure_reasons=["historical-failure"] if status == ModuleStatus.FAILED else [],
        retry_history=["retry-1"],
        needs_redecomposition=False,
        created_at="2026-04-22T12:00:00Z",
        updated_at="2026-04-22T12:00:00Z",
    )


def make_phase(
    phase_id: str,
    module_id: str,
    *,
    version: int,
    status: PhaseStatus = PhaseStatus.IN_PROGRESS,
    role: str | None = None,
    state_after: str | None = None,
    failure_reasons: list[str] | None = None,
) -> Phase:
    return Phase(
        phase_id=phase_id,
        module_id=module_id,
        experiment_id="exp-1",
        overview_version=version,
        phase_overview_ref=phase_id,
        name=phase_id,
        role=role or f"role-{phase_id}",
        state_after=state_after or f"state-{phase_id}",
        status=status,
        is_expanded=False,
        notes=[],
        failure_reasons=[] if failure_reasons is None else failure_reasons,
        retry_history=[],
        fallback_boundary="phase boundary",
        created_at="2026-04-22T12:00:00Z",
        updated_at="2026-04-22T12:00:00Z",
    )


def make_action(action_id: str = "action-1", *, guide_id: str = "guide-1", phase_id: str = "p1", module_id: str = "m1", version: int = 1) -> Action:
    return Action(
        action_id=action_id,
        experiment_id="exp-1",
        module_id=module_id,
        phase_id=phase_id,
        guide_id=guide_id,
        overview_version=version,
        title=action_id,
        action_type=ActionType.AUTO,
        executor_type=ActionExecutorHint.AGENT,
        instruction="do work",
        expected_output="output",
        required_inputs=[],
        decision_item_refs=[],
        done_check_refs=[],
        expected_output_refs=[],
        retry_policy="fixed",
        max_retry=1,
        priority=1,
        declared_order=0,
        status="running",
        current_attempt_index=1,
        retry_count=0,
        last_failure_reason=None,
        last_blocked_reason=None,
        last_record_id="record-1",
    )


def make_guide(
    *,
    guide_id: str = "guide-1",
    module_id: str = "m1",
    phase_id: str = "p1",
    version: int = 1,
    status: GuideStatus = GuideStatus.ACTIVE,
    with_open_items: bool = True,
) -> ExecutionGuide:
    return ExecutionGuide(
        guide_id=guide_id,
        experiment_id="exp-1",
        module_id=module_id,
        phase_id=phase_id,
        overview_version=version,
        guide_version=1,
        status=status,
        phase_problem="problem",
        decision_items=[
            DecisionItem(
                decision_id="decision-1",
                experiment_id="exp-1",
                module_id=module_id,
                phase_id=phase_id,
                guide_id=guide_id,
                overview_version=version,
                title="decision",
                decision_scope="phase",
                decision_type="generic",
                status="open",
                required_for_phase_done=True,
                created_at="2026-04-22T12:00:00Z",
                updated_at="2026-04-22T12:00:00Z",
            )
        ]
        if with_open_items
        else [],
        actions=[make_action(guide_id=guide_id, phase_id=phase_id, module_id=module_id, version=version)],
        done_criteria=[
            DoneCheck(
                check_id="check-1",
                experiment_id="exp-1",
                module_id=module_id,
                phase_id=phase_id,
                guide_id=guide_id,
                overview_version=version,
                check_scope="phase",
                title="check",
                check_type="evidence_bound",
                status="unmet",
                required=True,
                verifier_type="evidence_based",
                verifier_config={"source": "artifact"},
                created_at="2026-04-22T12:00:00Z",
                updated_at="2026-04-22T12:00:00Z",
            )
        ]
        if with_open_items
        else [],
        blockers=[],
        fallback_rule="stay inside phase",
        notes=[],
        created_from_phase_ref=phase_id,
        created_at="2026-04-22T12:00:00Z",
        superseded_by="migration-0" if status == GuideStatus.SUPERSEDED else None,
    )


def make_record(
    *,
    record_id: str = "record-1",
    action_id: str = "action-1",
    guide_id: str = "guide-1",
    module_id: str = "m1",
    phase_id: str = "p1",
    version: int = 1,
    status: str = "running",
    finalized: bool | None = None,
    counts_as_retry: bool = False,
) -> ActionRecord:
    blocked_reason = None
    waiting_target = None
    failure_reason = None
    if status == "blocked":
        blocked_reason = BlockedReason(
            blocked_reason_type="external_tool_not_ready",
            code="wait-tool",
            message="wait",
            retryable_after_unblock=True,
        )
        waiting_target = WaitingTarget(waiting_type="external_tool", target_id="tool", correlation_key="corr-1")
    if status == "failed":
        failure_reason = FailureReason(
            category="permanent_failure",
            code="failure-code",
            message="failed",
            retryable=False,
            counts_as_retry=counts_as_retry,
        )
    return ActionRecord(
        action_record_id=record_id,
        experiment_id="exp-1",
        module_id=module_id,
        phase_id=phase_id,
        guide_id=guide_id,
        action_id=action_id,
        overview_version=version,
        attempt_index=1,
        parent_attempt_index=None,
        action_type=ActionType.AUTO,
        executor_type="agent",
        attempt_status=status,
        finalized=(status in {"done", "failed", "abandoned"}) if finalized is None else finalized,
        record_integrity="valid",
        input_snapshot={},
        execution_payload=None,
        output_snapshot={"ok": True} if status == "done" else None,
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
        evidence_refs=[],
        phase_writeback_hint="done" if status == "done" else ("blocked" if status == "blocked" else "in_progress"),
        counts_as_retry=counts_as_retry,
        selected_at="2026-04-22T12:00:00Z",
        started_at="2026-04-22T12:01:00Z" if status in {"running", "done", "failed"} else None,
        terminal_at="2026-04-22T12:02:00Z" if status in {"done", "failed", "abandoned"} else None,
        created_at="2026-04-22T12:00:00Z",
        finalized_at="2026-04-22T12:03:00Z" if status in {"done", "failed", "abandoned"} else None,
        external_correlation_key=None,
        record_revision=1,
        mutation_reason_code="seed",
        mutation_log_required=False,
    )


def baseline_context(*, with_open_guide_items: bool = False) -> dict:
    old_overview = make_overview(1, [("m1", ["p1", "p2"]), ("m2", ["p3"])])
    new_overview = make_overview(2, [("m1", ["p1", "p2"]), ("m2", ["p3"])])
    old_modules = [make_module("m1", ["p1", "p2"], version=1), make_module("m2", ["p3"], version=1, status=ModuleStatus.NOT_STARTED)]
    old_phases = [
        make_phase("p1", "m1", version=1, status=PhaseStatus.IN_PROGRESS),
        make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED),
        make_phase("p3", "m2", version=1, status=PhaseStatus.NOT_STARTED),
    ]
    old_guides = [make_guide(with_open_items=with_open_guide_items)]
    old_records = [make_record(status="running")]
    module_mapping = [
        ModuleMigrationItem(old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
        ModuleMigrationItem(old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
    ]
    phase_mapping = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ]
    return {
        "old_overview": old_overview,
        "new_overview": new_overview,
        "old_modules": old_modules,
        "old_phases": old_phases,
        "old_guides": old_guides,
        "old_action_records": old_records,
        "module_mapping": module_mapping,
        "phase_mapping": phase_mapping,
        "created_at": "2026-04-22T13:00:00Z",
    }


def run_migration(**overrides):
    context = baseline_context(with_open_guide_items=overrides.pop("with_open_guide_items", False))
    context.update(overrides)
    return migrate_overview(migration_id="migration-1", **context)


def test_migration_input_validation_and_mapping_completeness() -> None:
    context = baseline_context()

    with pytest.raises(ValueError, match="missing v_old overview"):
        migrate_overview(migration_id="migration-1", old_overview=None, **{key: value for key, value in context.items() if key != "old_overview"})

    with pytest.raises(ValueError, match="missing v_new overview"):
        migrate_overview(migration_id="migration-1", new_overview=None, **{key: value for key, value in context.items() if key != "new_overview"})

    with pytest.raises(ValueError, match="missing old runtime objects"):
        migrate_overview(migration_id="migration-1", **{**context, "old_modules": None})

    paused_missing = run_migration(module_mapping=[], phase_mapping=context["phase_mapping"])
    assert paused_missing.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert paused_missing.migration.pause_reason_code == "incomplete_mapping"

    paused_incomplete = run_migration(phase_mapping=context["phase_mapping"][:-1])
    assert paused_incomplete.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert has_complete_mapping(context["old_overview"], context["new_overview"], context["module_mapping"], context["phase_mapping"]) is True


def test_version_boundary_and_overview_setup() -> None:
    result = run_migration()

    assert result.kind == MigrationOutcomeKind.AUTO_RESUMED
    assert result.old_overview.version == 1
    assert result.new_overview.version == 2
    assert result.old_overview.superseded_by_version == 2
    assert result.new_overview.parent_version == 1
    assert result.new_overview.structural_change_summary
    assert result.new_modules[0].overview_version == 2
    assert result.new_phases[0].overview_version == 2
    assert result.old_overview.modules[0].overview_version == 1
    assert result.new_overview.modules[0].overview_version == 2


def test_freeze_behavior_and_frozen_record_write_rejection() -> None:
    context = baseline_context()
    frozen_guides, frozen_records = freeze_old_active_runtime(
        context["old_guides"],
        context["old_action_records"],
        migration_id="migration-1",
        to_overview_version=2,
    )

    assert frozen_guides[0].status == GuideStatus.SUPERSEDED
    assert frozen_guides[0].superseded_by == "migration-1"
    assert frozen_guides[0].actions[0].status is None
    assert frozen_guides[0].actions[0].current_attempt_index is None
    assert frozen_records[0].frozen_by_migration_id == "migration-1"

    with pytest.raises(ValueError, match="migration-frozen action records cannot be business-state mutated"):
        start_running(frozen_records[0], started_at="2026-04-22T13:10:00Z")


def test_build_helpers_and_module_recomputation_do_not_blindly_copy_runtime_truth() -> None:
    context = baseline_context()
    context["old_modules"][0].current_phase_id = "p1"
    context["old_modules"][0].blocked_phase_ids = ["p2"]
    context["old_phases"][0] = make_phase("p1", "m1", version=1, status=PhaseStatus.DONE)
    result = run_migration(**context)

    new_module = next(module for module in result.new_modules if module.module_id == "m1")
    assert "note-1" in new_module.notes
    assert new_module.current_phase_id == "p2"
    assert new_module.blocked_phase_ids == []
    assert new_module.status == ModuleStatus.NOT_STARTED


def test_phase_mapping_rules_for_unchanged_and_semantic_change() -> None:
    old_phases = [
        make_phase("p1", "m1", version=1, status=PhaseStatus.DONE),
        make_phase("p2", "m1", version=1, status=PhaseStatus.BLOCKED, failure_reasons=["external_tool_not_ready"]),
    ]
    new_overview = make_overview(2, [("m1", ["p1", "p2"])])
    new_phases = build_phases_from_overview(new_overview)
    mapping = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ]

    migrated, kind, reason = handle_phase_mapping(old_phases, new_phases, mapping)
    assert kind is None and reason is None
    assert next(phase for phase in migrated if phase.phase_id == "p1").status == PhaseStatus.DONE
    assert next(phase for phase in migrated if phase.phase_id == "p2").status == PhaseStatus.BLOCKED

    changed = [phase.model_copy(update={"role": "different"}) if phase.phase_id == "p1" else phase for phase in new_phases]
    migrated_changed, _, _ = handle_phase_mapping(old_phases, changed, mapping)
    assert next(phase for phase in migrated_changed if phase.phase_id == "p1").status == PhaseStatus.NOT_STARTED


def test_split_phase_rules_cover_unique_and_ambiguous_cases() -> None:
    old_phase = [make_phase("p1", "m1", version=1, status=PhaseStatus.DONE)]
    new_overview = make_overview(2, [("m1", ["p1a", "p1b"])])
    new_phases = build_phases_from_overview(new_overview)
    unique_mapping = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1a", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="inherited", state_inheritance_mode="partial", terminality_preserved=False, reason_code="unique_coverage"),
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1b", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
    ]
    migrated, kind, reason = handle_phase_mapping(old_phase, new_phases, unique_mapping)
    assert kind is None and reason is None
    assert next(phase for phase in migrated if phase.phase_id == "p1a").status == PhaseStatus.DONE
    assert next(phase for phase in migrated if phase.phase_id == "p1b").status == PhaseStatus.NOT_STARTED

    ambiguous_mapping = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1a", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1b", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
    ]
    _, kind, reason = handle_phase_mapping(old_phase, new_phases, ambiguous_mapping)
    assert kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert reason == "split_phase_coverage_ambiguous"


def test_split_in_progress_continuation_requires_semantic_uniqueness() -> None:
    unique_result = run_migration(
        new_overview=make_overview(2, [("m1", ["p1a", "p1b", "p2"]), ("m2", ["p3"])]),
        phase_mapping=[
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1a", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="inherited", state_inheritance_mode="partial", terminality_preserved=False, reason_code="unique_coverage"),
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1b", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
            PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
            PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        ],
    )
    assert unique_result.kind == MigrationOutcomeKind.AUTO_RESUMED
    assert unique_result.migration.resume_phase_id == "p1a"

    ambiguous_result = run_migration(
        new_overview=make_overview(2, [("m1", ["p1a", "p1b", "p2"]), ("m2", ["p3"])]),
        phase_mapping=[
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1a", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1b", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
            PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
            PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        ],
    )
    assert ambiguous_result.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert ambiguous_result.reason == "split_phase_coverage_ambiguous"
    assert ambiguous_result.migration.pause_reason_code == "split_phase_coverage_ambiguous"


def test_split_module_ambiguity_does_not_fall_back_to_module_order() -> None:
    result = run_migration(
        new_overview=make_overview(2, [("m1a", ["p1"]), ("m1b", ["p2"]), ("m2", ["p3"])]),
        module_mapping=[
            ModuleMigrationItem(old_module_id="m1", new_module_id="m1a", mapping_type="split", migration_result="paused", state_inheritance_mode="reset"),
            ModuleMigrationItem(old_module_id="m1", new_module_id="m1b", mapping_type="split", migration_result="paused", state_inheritance_mode="reset"),
            ModuleMigrationItem(old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
        ],
        phase_mapping=[
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1a", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
            PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1b", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
            PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        ],
    )
    assert result.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert result.reason == "split_module_coverage_ambiguous"


def test_merged_phase_rules_cover_done_partial_and_conflicts() -> None:
    new_overview = make_overview(2, [("m1", ["p12"])])
    new_phases = build_phases_from_overview(new_overview)
    mapping = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p12", old_module_id="m1", new_module_id="m1", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p12", old_module_id="m1", new_module_id="m1", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial", terminality_preserved=False),
    ]

    done_sources = [make_phase("p1", "m1", version=1, status=PhaseStatus.DONE), make_phase("p2", "m1", version=1, status=PhaseStatus.DONE)]
    migrated_done, kind_done, _ = handle_phase_mapping(done_sources, new_phases, mapping)
    assert kind_done is None
    assert migrated_done[0].status == PhaseStatus.DONE

    partial_sources = [make_phase("p1", "m1", version=1, status=PhaseStatus.DONE), make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED)]
    migrated_partial, kind_partial, _ = handle_phase_mapping(partial_sources, new_phases, mapping)
    assert kind_partial is None
    assert migrated_partial[0].status == PhaseStatus.IN_PROGRESS

    conflicting_sources = [
        make_phase("p1", "m1", version=1, status=PhaseStatus.BLOCKED, failure_reasons=["external_tool_not_ready"]),
        make_phase("p2", "m1", version=1, status=PhaseStatus.FAILED, failure_reasons=["hard-failure"]),
    ]
    _, kind_conflict, reason_conflict = handle_phase_mapping(conflicting_sources, new_phases, mapping)
    assert kind_conflict == MigrationOutcomeKind.ESCALATE_MIGRATION
    assert reason_conflict == "merged_phase_conflict"


def test_failed_phase_migration_routes_repaired_pause_and_escalate() -> None:
    new_overview = make_overview(2, [("m1", ["p1"]), ("m2", ["p3"])])
    repaired = run_migration(
        new_overview=new_overview,
        old_phases=[
            make_phase("p1", "m1", version=1, status=PhaseStatus.FAILED, failure_reasons=["undeclared_dependency"]),
            make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED),
            make_phase("p3", "m2", version=1, status=PhaseStatus.NOT_STARTED),
        ],
        phase_mapping=[
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="reset", terminality_preserved=False, reason_code="repaired"),
            PhaseMigrationItem(old_phase_id="p2", new_phase_id=None, old_module_id="m1", new_module_id=None, mapping_type="removed", migration_result="obsolete", state_inheritance_mode="none", terminality_preserved=False),
            PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        ],
    )
    repaired_phase = next(phase for phase in repaired.new_phases if phase.phase_id == "p1")
    assert repaired.kind == MigrationOutcomeKind.AUTO_RESUMED
    assert repaired_phase.status == PhaseStatus.NOT_STARTED

    paused = run_migration(
        old_phases=[
            make_phase("p1", "m1", version=1, status=PhaseStatus.FAILED, failure_reasons=["undeclared_dependency"]),
            make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED),
            make_phase("p3", "m2", version=1, status=PhaseStatus.NOT_STARTED),
        ],
        phase_mapping=[
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False, reason_code="repair_status_unknown"),
            PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
            PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        ],
    )
    assert paused.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert paused.reason == "failed_phase_repair_indeterminate"

    escalated = run_migration(
        old_phases=[
            make_phase("p1", "m1", version=1, status=PhaseStatus.FAILED, failure_reasons=["fallback_boundary_violation"]),
            make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED),
            make_phase("p3", "m2", version=1, status=PhaseStatus.NOT_STARTED),
        ],
        phase_mapping=[
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="escalated", state_inheritance_mode="copy", terminality_preserved=True, reason_code="still_broken"),
            PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
            PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        ],
    )
    assert escalated.kind == MigrationOutcomeKind.ESCALATE_MIGRATION
    assert escalated.reason == "fallback_boundary_violation_still_present"


def test_removed_and_reordered_phase_behaviors_route_correctly() -> None:
    removed_context = baseline_context(with_open_guide_items=True)
    removed_context["new_overview"] = make_overview(2, [("m1", ["p2"]), ("m2", ["p3"])])
    removed_context["phase_mapping"] = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id=None, old_module_id="m1", new_module_id=None, mapping_type="removed", migration_result="obsolete", state_inheritance_mode="none", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ]
    removed_context["old_phases"][0] = make_phase("p1", "m1", version=1, status=PhaseStatus.IN_PROGRESS)
    removed_context["old_phases"][1] = make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED)
    removed_result = run_migration(**removed_context)
    assert removed_result.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert removed_result.reason == "guide_mapping_not_unique"

    reordered_context = baseline_context()
    reordered_context["new_overview"] = make_overview(2, [("m1", ["p2", "p1"]), ("m2", ["p3"])])
    reordered_context["old_phases"][0] = make_phase("p1", "m1", version=1, status=PhaseStatus.IN_PROGRESS)
    reordered_context["old_phases"][1] = make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED)
    reordered_context["phase_mapping"] = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="reordered", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="reordered", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ]
    reordered_result = run_migration(**reordered_context)
    assert reordered_result.kind == MigrationOutcomeKind.AUTO_RESUMED
    assert reordered_result.migration.resume_phase_id == "p2"


def test_reordered_predecessor_fallback_is_explicit_and_can_pause() -> None:
    one_predecessor = baseline_context()
    one_predecessor["new_overview"] = make_overview(2, [("m1", ["p0", "p1", "p2"]), ("m2", ["p3"])])
    one_predecessor["old_guides"] = [make_guide(phase_id="p1")]
    one_predecessor["old_phases"] = [
        make_phase("p1", "m1", version=1, status=PhaseStatus.IN_PROGRESS),
        make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED),
        make_phase("p3", "m2", version=1, status=PhaseStatus.NOT_STARTED),
    ]
    one_predecessor["phase_mapping"] = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="reordered", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id=None, new_phase_id="p0", old_module_id=None, new_module_id="m1", mapping_type="created", migration_result="inherited", state_inheritance_mode="none", terminality_preserved=False),
    ]
    one_predecessor["module_mapping"] = [
        ModuleMigrationItem(old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
        ModuleMigrationItem(old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
    ]
    resumed = run_migration(**one_predecessor)
    assert resumed.kind == MigrationOutcomeKind.AUTO_RESUMED
    assert resumed.migration.resume_phase_id == "p0"

    ambiguous = baseline_context()
    ambiguous["old_overview"] = make_overview(1, [("m1", ["p0", "p1", "p2"]), ("m2", ["p3"])])
    ambiguous["new_overview"] = make_overview(2, [("m1", ["p0a", "p0b", "p1", "p2"]), ("m2", ["p3"])])
    ambiguous["old_modules"] = [make_module("m1", ["p0", "p1", "p2"], version=1), make_module("m2", ["p3"], version=1, status=ModuleStatus.NOT_STARTED)]
    ambiguous["old_guides"] = [make_guide(phase_id="p1")]
    ambiguous["old_phases"] = [
        make_phase("p0", "m1", version=1, status=PhaseStatus.NOT_STARTED),
        make_phase("p1", "m1", version=1, status=PhaseStatus.IN_PROGRESS),
        make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED),
        make_phase("p3", "m2", version=1, status=PhaseStatus.NOT_STARTED),
    ]
    ambiguous["phase_mapping"] = [
        PhaseMigrationItem(old_phase_id="p0", new_phase_id="p0a", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p0", new_phase_id="p0b", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="reordered", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ]
    ambiguous_result = run_migration(**ambiguous)
    assert ambiguous_result.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert ambiguous_result.reason == "ambiguous_resume_phase"

    no_new_predecessor = baseline_context()
    no_new_predecessor["new_overview"] = make_overview(2, [("m1", ["p1", "p2"]), ("m2", ["p3"])])
    no_new_predecessor["old_guides"] = [make_guide(phase_id="p1")]
    normal_result = run_migration(**no_new_predecessor)
    assert normal_result.kind == MigrationOutcomeKind.AUTO_RESUMED
    assert normal_result.migration.resume_phase_id == "p1"


def test_module_mapping_classes_cover_removed_split_merged_and_reordered() -> None:
    context = baseline_context()
    context["new_overview"] = make_overview(2, [("m1a", ["p1"]), ("m1b", ["p2"]), ("m2", ["p3"])])
    context["module_mapping"] = [
        ModuleMigrationItem(old_module_id="m1", new_module_id="m1a", mapping_type="split", migration_result="paused", state_inheritance_mode="partial"),
        ModuleMigrationItem(old_module_id="m1", new_module_id="m1b", mapping_type="split", migration_result="paused", state_inheritance_mode="reset"),
        ModuleMigrationItem(old_module_id="m2", new_module_id="m2", mapping_type="reordered", migration_result="inherited", state_inheritance_mode="copy"),
    ]
    context["phase_mapping"] = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1a", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1b", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ]
    split_result = run_migration(**context)
    assert split_result.kind == MigrationOutcomeKind.AUTO_RESUMED

    merged_overview = make_overview(2, [("m12", ["p1", "p2", "p3"])])
    merged_context = baseline_context()
    merged_context["new_overview"] = merged_overview
    merged_context["module_mapping"] = [
        ModuleMigrationItem(old_module_id="m1", new_module_id="m12", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial"),
        ModuleMigrationItem(old_module_id="m2", new_module_id="m12", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial"),
    ]
    merged_context["phase_mapping"] = [
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m12", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m12", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m12", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ]
    merged_result = run_migration(**merged_context)
    assert merged_result.kind == MigrationOutcomeKind.AUTO_RESUMED

    removed_modules = [
        ModuleMigrationItem(old_module_id="m1", new_module_id=None, mapping_type="removed", migration_result="obsolete", state_inheritance_mode="none"),
        ModuleMigrationItem(old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
    ]
    assert removed_modules[0].mapping_type == MigrationMappingType.REMOVED


def test_execution_guide_migration_rules() -> None:
    auto = run_migration()
    assert all(guide.status == GuideStatus.SUPERSEDED for guide in auto.old_guides)
    assert all(guide.guide_id != auto.new_guide.guide_id for guide in auto.old_guides if auto.new_guide is not None)
    assert auto.new_guide is not None
    assert auto.new_guide.overview_version == 2

    paused = run_migration(with_open_guide_items=True, phase_mapping=[
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1a", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="partial", terminality_preserved=False, reason_code="unique_coverage"),
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1b", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
    ], new_overview=make_overview(2, [("m1", ["p1a", "p1b", "p2"]), ("m2", ["p3"])]))
    assert paused.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert paused.new_guide is None


def test_action_record_migration_preserves_truth_and_adds_only_context() -> None:
    result = run_migration()
    original = baseline_context()["old_action_records"][0]
    relinked = result.historical_action_records[0]

    assert relinked.attempt_status == original.attempt_status
    assert relinked.phase_writeback_hint == original.phase_writeback_hint
    assert relinked.attempt_index == original.attempt_index
    assert relinked.finalized == original.finalized
    assert relinked.migrated_to_overview_version == 2
    assert relinked.migrated_resume_module_id == result.migration.resume_module_id
    assert relinked.migrated_resume_phase_id == result.migration.resume_phase_id

    waiting_context = baseline_context()
    waiting_context["old_action_records"] = [make_record(status="blocked")]
    waiting_result = run_migration(**waiting_context)
    waiting_record = waiting_result.historical_action_records[0]
    assert waiting_record.attempt_status == "blocked"
    assert waiting_record.waiting_target is not None
    assert waiting_result.new_guide is not None

    finalized_record = make_record(status="done")
    relinked_finalized = relink_historical_action_records(
        [finalized_record],
        migration_id="migration-1",
        resume_module_id="m1",
        resume_phase_id="p1",
        to_overview_version=2,
    )[0]
    assert relinked_finalized.finalized is True


def test_historical_action_record_truth_fields_remain_immutable_across_migration() -> None:
    finalized_original = make_record(status="done")
    finalized_result = run_migration(old_action_records=[finalized_original])
    finalized_relinked = finalized_result.historical_action_records[0]
    assert finalized_relinked.attempt_status == finalized_original.attempt_status
    assert finalized_relinked.failure_reason == finalized_original.failure_reason
    assert finalized_relinked.blocked_reason == finalized_original.blocked_reason
    assert finalized_relinked.counts_as_retry == finalized_original.counts_as_retry
    assert finalized_relinked.finalized == finalized_original.finalized
    assert finalized_relinked.migrated_resume_phase_id == finalized_result.migration.resume_phase_id
    assert finalized_relinked.record_revision == finalized_original.record_revision + 1

    blocked_original = make_record(status="blocked")
    blocked_result = run_migration(old_action_records=[blocked_original])
    blocked_relinked = blocked_result.historical_action_records[0]
    assert blocked_relinked.attempt_status == blocked_original.attempt_status
    assert blocked_relinked.blocked_reason == blocked_original.blocked_reason
    assert blocked_relinked.finalized == blocked_original.finalized

    failed_original = make_record(status="failed", counts_as_retry=True)
    failed_result = run_migration(old_action_records=[failed_original])
    failed_relinked = failed_result.historical_action_records[0]
    assert failed_relinked.attempt_status == failed_original.attempt_status
    assert failed_relinked.failure_reason == failed_original.failure_reason
    assert failed_relinked.counts_as_retry is True
    assert failed_relinked.finalized == failed_original.finalized
    assert failed_relinked.mutation_reason_code == "migration_relinked"


def test_resume_point_resolution_priority_and_tie_breaks() -> None:
    overview = make_overview(2, [("m1", ["p1", "p2"]), ("m2", ["p3"])])
    modules = build_modules_from_overview(
        overview,
        [
            ModuleMigrationItem(old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
            ModuleMigrationItem(old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
        ],
        [make_module("m1", ["p1", "p2"], version=1), make_module("m2", ["p3"], version=1)],
    )
    phases = build_phases_from_overview(overview)

    in_progress_phases = [
        phases[0].model_copy(update={"status": PhaseStatus.IN_PROGRESS}),
        phases[1].model_copy(update={"status": PhaseStatus.NOT_STARTED}),
        phases[2].model_copy(update={"status": PhaseStatus.NOT_STARTED}),
    ]
    assert resolve_resume_module(modules, in_progress_phases, overview) == "m1"
    assert resolve_resume_phase("m1", in_progress_phases, overview) == "p1"

    waiting_phases = [
        phases[0].model_copy(update={"status": PhaseStatus.DONE}),
        phases[1].model_copy(update={"status": PhaseStatus.BLOCKED, "failure_reasons": ["external_tool_not_ready"]}),
        phases[2].model_copy(update={"status": PhaseStatus.NOT_STARTED}),
    ]
    assert resolve_resume_module(modules, waiting_phases, overview) == "m1"
    assert resolve_resume_phase("m1", waiting_phases, overview) == "p2"

    unfinished_phases = [
        phases[0].model_copy(update={"status": PhaseStatus.DONE}),
        phases[1].model_copy(update={"status": PhaseStatus.NOT_STARTED}),
        phases[2].model_copy(update={"status": PhaseStatus.NOT_STARTED}),
    ]
    assert resolve_resume_module(modules, unfinished_phases, overview) == "m1"
    assert resolve_resume_phase("m1", unfinished_phases, overview) == "p2"


def test_resume_resolution_pause_and_escalate_routes() -> None:
    broken_overview = make_overview(2, [("m1", ["p1"])], depends_on_by_module={"m1": ["missing-module"]})
    broken_result = run_migration(new_overview=broken_overview, module_mapping=[
        ModuleMigrationItem(old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy"),
        ModuleMigrationItem(old_module_id="m2", new_module_id="m1", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial"),
    ], phase_mapping=[
        PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p2", new_phase_id="p1", old_module_id="m1", new_module_id="m1", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial", terminality_preserved=False),
        PhaseMigrationItem(old_phase_id="p3", new_phase_id="p1", old_module_id="m2", new_module_id="m1", mapping_type="merged", migration_result="inherited", state_inheritance_mode="partial", terminality_preserved=False),
    ])
    assert broken_result.kind == MigrationOutcomeKind.ESCALATE_MIGRATION
    assert broken_result.migration.escalate_reason_code == "undeclared_dependency_still_present"

    split_pause = run_migration(
        new_overview=make_overview(2, [("m1", ["p1a", "p1b", "p2"]), ("m2", ["p3"])]),
        old_phases=[
            make_phase("p1", "m1", version=1, status=PhaseStatus.DONE),
            make_phase("p2", "m1", version=1, status=PhaseStatus.NOT_STARTED),
            make_phase("p3", "m2", version=1, status=PhaseStatus.NOT_STARTED),
        ],
        phase_mapping=[
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1a", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
            PhaseMigrationItem(old_phase_id="p1", new_phase_id="p1b", old_module_id="m1", new_module_id="m1", mapping_type="split", migration_result="paused", state_inheritance_mode="reset", terminality_preserved=False),
            PhaseMigrationItem(old_phase_id="p2", new_phase_id="p2", old_module_id="m1", new_module_id="m1", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
            PhaseMigrationItem(old_phase_id="p3", new_phase_id="p3", old_module_id="m2", new_module_id="m2", mapping_type="unchanged", migration_result="inherited", state_inheritance_mode="copy", terminality_preserved=True),
        ],
    )
    assert split_pause.kind == MigrationOutcomeKind.PAUSE_MIGRATION


def test_active_attempt_conflict_and_boundary_escalations() -> None:
    conflict_result = run_migration(old_action_records=[
        make_record(record_id="record-1", status="running"),
        make_record(record_id="record-2", status="blocked"),
    ])
    assert conflict_result.kind == MigrationOutcomeKind.ESCALATE_MIGRATION
    assert conflict_result.reason == "active_attempt_conflict"

    fallback_context = baseline_context()
    fallback_context["old_phases"][0] = make_phase("p1", "m1", version=1, status=PhaseStatus.FAILED, failure_reasons=["fallback_boundary_violation"])
    fallback_result = run_migration(**fallback_context)
    assert fallback_result.kind == MigrationOutcomeKind.PAUSE_MIGRATION
    assert fallback_result.reason == "failed_phase_repair_indeterminate"


def test_safety_guards_and_result_explicitness() -> None:
    result = run_migration()
    assert result.kind in {
        MigrationOutcomeKind.AUTO_RESUMED,
        MigrationOutcomeKind.PAUSE_MIGRATION,
        MigrationOutcomeKind.ESCALATE_MIGRATION,
    }
    assert all(guide.status != GuideStatus.ACTIVE for guide in result.old_guides)
    assert result.migration.migration_status == MigrationStatus.COMPLETED

    with pytest.raises(ValidationError):
        ModuleMigrationItem(old_module_id=None, new_module_id=None, mapping_type="unchanged", migration_result="paused", state_inheritance_mode="none")
