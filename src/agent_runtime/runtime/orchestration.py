"""Explicit Phase 6 orchestration handlers."""

from __future__ import annotations

from collections.abc import Callable

from agent_runtime.acceptance import (
    AdoptionEvaluationKind,
    ExperimentGateKind,
    ModuleGateKind,
    PhaseGateKind,
    evaluate_adoption_candidate,
    evaluate_experiment_gate,
    evaluate_module_gate,
    evaluate_phase_gate,
)
from agent_runtime.migration import MigrationOutcomeKind, MigrationRunResult
from agent_runtime.models import AdoptedDesignItem, ExecutionGuide, PhaseStatus
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

from .results import (
    AcceptanceEvaluationResult,
    ExecutionWritebackResult,
    RuntimeMigrationKind,
    RuntimeMigrationResult,
)
from .state import RuntimeState, RuntimeStatus


def apply_migration_result(state: RuntimeState, result: RuntimeMigrationResult) -> None:
    if result.kind == RuntimeMigrationKind.AUTO_RESUMED:
        if result.overview is None or result.resume_module_id is None or result.resume_phase_id is None:
            state.runtime_status = RuntimeStatus.ESCALATED
            state.issue_evidence.append("migration_missing_unique_resume_point")
            return
        state.overview = result.overview
        state.modules = result.modules
        state.phases = result.phases
        state.guides = result.guides
        state.current_overview_version = result.overview.version
        state.current_module_id = result.resume_module_id
        state.current_phase_id = result.resume_phase_id
        state.current_guide_id = None
        state.current_action_id = None
        state.waiting_context = None
        return
    if result.kind == RuntimeMigrationKind.PAUSE_MIGRATION:
        state.runtime_status = RuntimeStatus.PAUSED
        return
    if result.kind == RuntimeMigrationKind.ESCALATE_MIGRATION:
        state.runtime_status = RuntimeStatus.ESCALATED
        return
    raise ValueError(f"unsupported migration result: {result.kind}")


def migration_run_to_runtime_result(result: MigrationRunResult) -> RuntimeMigrationResult:
    if result.kind == MigrationOutcomeKind.AUTO_RESUMED:
        guides = [result.new_guide] if result.new_guide is not None else []
        return RuntimeMigrationResult(
            kind=RuntimeMigrationKind.AUTO_RESUMED,
            overview=result.new_overview,
            modules=result.new_modules,
            phases=result.new_phases,
            guides=guides,
            resume_module_id=result.migration.resume_module_id,
            resume_phase_id=result.migration.resume_phase_id,
            reason=result.reason,
        )
    if result.kind == MigrationOutcomeKind.PAUSE_MIGRATION:
        return RuntimeMigrationResult(kind=RuntimeMigrationKind.PAUSE_MIGRATION, reason=result.reason)
    if result.kind == MigrationOutcomeKind.ESCALATE_MIGRATION:
        return RuntimeMigrationResult(kind=RuntimeMigrationKind.ESCALATE_MIGRATION, reason=result.reason)
    raise ValueError(f"unsupported migration outcome: {result.kind}")


def run_overview_revision_and_migration(
    state: RuntimeState,
    *,
    migration_runner: Callable[[RuntimeState], RuntimeMigrationResult | MigrationRunResult] | None = None,
) -> RuntimeMigrationResult:
    """Fixed revision+migration subflow boundary for Phase 6.

    Prompt generation and audit are intentionally external to this phase. The provided
    runner represents the already-defined revision/audit/migration stack.
    """

    if migration_runner is None:
        return RuntimeMigrationResult(
            kind=RuntimeMigrationKind.ESCALATE_MIGRATION,
            reason="overview_revision_migration_runner_missing",
        )
    result = migration_runner(state)
    if isinstance(result, MigrationRunResult):
        return migration_run_to_runtime_result(result)
    return result


def handle_module_result(state: RuntimeState, result: ModuleResolution) -> str:
    if result.kind == ModuleResolutionKind.KEEP_CURRENT_MODULE:
        if result.module_id is not None:
            state.current_module_id = result.module_id
        return "continue_stages"
    if result.kind == ModuleResolutionKind.SWITCH_MODULE:
        state.current_module_id = result.module_id
        state.current_phase_id = None
        state.current_guide_id = None
        state.current_action_id = None
        return "continue_loop"
    if result.kind == ModuleResolutionKind.PAUSE_MODULE:
        state.runtime_status = RuntimeStatus.PAUSED
        return "terminal"
    if result.kind == ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION:
        return "migrate"
    raise ValueError(f"unsupported module resolution: {result.kind}")


def handle_phase_result(state: RuntimeState, result: PhaseResolution) -> str:
    if result.kind == PhaseResolutionKind.KEEP_CURRENT_PHASE:
        if result.phase_id is not None:
            state.current_phase_id = result.phase_id
        return "continue_stages"
    if result.kind == PhaseResolutionKind.SWITCH_PHASE:
        state.current_phase_id = result.phase_id
        state.current_guide_id = None
        state.current_action_id = None
        return "continue_loop"
    if result.kind in {
        PhaseResolutionKind.PAUSE_WAIT_EXTERNAL_TOOL_RESULT,
        PhaseResolutionKind.PAUSE_WAIT_HUMAN_INPUT,
        PhaseResolutionKind.PAUSE_WAIT_EXTERNAL_RESOURCE,
    }:
        state.runtime_status = RuntimeStatus.PAUSED
        state.waiting_context = {"origin": result.kind.value, "phase_id": state.current_phase_id}
        return "terminal"
    if result.kind == PhaseResolutionKind.REVISE_GUIDE_KEEP_PHASE:
        state.current_guide_id = None
        state.current_action_id = None
        return "continue_loop"
    if result.kind == PhaseResolutionKind.ESCALATE_TO_OVERVIEW_REVISION:
        return "migrate"
    raise ValueError(f"unsupported phase resolution: {result.kind}")


def handle_guide_result(state: RuntimeState, result: GuideResolution) -> str:
    if result.kind == GuideResolutionKind.USE_GUIDE:
        state.current_guide_id = result.guide_id
        return "continue_stages"
    if result.kind == GuideResolutionKind.REVISE_GUIDE_KEEP_PHASE:
        state.current_guide_id = None
        state.current_action_id = None
        return "continue_loop"
    if result.kind == GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION:
        return "migrate"
    raise ValueError(f"unsupported guide resolution: {result.kind}")


def resolve_bound_current_guide(state: RuntimeState) -> ExecutionGuide | None:
    if state.current_guide_id is None:
        state.issue_evidence.append("current_guide_missing")
        return None
    matches = [guide for guide in state.guides if guide.guide_id == state.current_guide_id]
    if len(matches) != 1:
        state.issue_evidence.append("current_guide_not_uniquely_bound")
        return None
    return matches[0]


def handle_action_result(state: RuntimeState, result: ActionResolution) -> str:
    if result.kind in {ActionResolutionKind.CONTINUE_CURRENT_ACTION, ActionResolutionKind.RETRY_CURRENT_ACTION}:
        state.current_action_id = result.action_id or state.current_action_id
        return "execute"
    if result.kind == ActionResolutionKind.ABANDON_CURRENT_ACTION_AND_SWITCH:
        state.current_action_id = result.action_id
        return "execute"
    if result.kind in {
        ActionResolutionKind.PAUSE_WAIT_EXTERNAL_TOOL_RESULT,
        ActionResolutionKind.PAUSE_WAIT_HUMAN_INPUT,
        ActionResolutionKind.PAUSE_WAIT_EXTERNAL_RESOURCE,
        ActionResolutionKind.NO_EXECUTABLE_ACTION_PAUSE,
    }:
        if result.action_id is not None:
            state.current_action_id = result.action_id
        state.runtime_status = RuntimeStatus.PAUSED
        state.waiting_context = {"origin": result.kind.value, "action_id": state.current_action_id}
        return "terminal"
    if result.kind in {ActionResolutionKind.REVISE_GUIDE_KEEP_PHASE, ActionResolutionKind.NO_EXECUTABLE_ACTION_REVISE_GUIDE}:
        state.current_guide_id = None
        state.current_action_id = None
        return "continue_loop"
    if result.kind in {ActionResolutionKind.ESCALATE_TO_OVERVIEW_REVISION, ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE}:
        return "migrate"
    raise ValueError(f"unsupported action resolution: {result.kind}")


def handle_execution_writeback(state: RuntimeState, result: ExecutionWritebackResult | None) -> str:
    if result is None:
        return "continue_stages"
    if result.action_records is not None:
        state.action_records = list(result.action_records)
    if result.action_id is not None:
        state.current_action_id = result.action_id
    if result.clear_current_action:
        state.current_action_id = None
    if result.waiting_context is not None:
        state.waiting_context = result.waiting_context
    if result.runtime_status == RuntimeStatus.PAUSED:
        state.runtime_status = RuntimeStatus.PAUSED
        return "terminal"
    if result.runtime_status == RuntimeStatus.ESCALATED:
        state.runtime_status = RuntimeStatus.ESCALATED
        return "terminal"
    if result.runtime_status == RuntimeStatus.COMPLETED:
        state.runtime_status = RuntimeStatus.COMPLETED
        return "terminal"
    return "continue_stages"


def evaluate_acceptance_and_promotion(state: RuntimeState) -> list[AcceptanceEvaluationResult]:
    current_phase = next((phase for phase in state.phases if phase.phase_id == state.current_phase_id), None)
    current_module = next((module for module in state.modules if module.module_id == state.current_module_id), None)
    current_guide = next((guide for guide in state.guides if guide.guide_id == state.current_guide_id), None)
    if current_phase is None or current_module is None:
        return [AcceptanceEvaluationResult(kind="keep_current_state", reason="current_scope_unresolved")]

    decisions = current_guide.decision_items if current_guide is not None else []
    checks = current_guide.done_criteria if current_guide is not None else []
    phase_result = evaluate_phase_gate(
        current_phase,
        decision_items=decisions,
        done_checks=checks,
        action_records=state.action_records,
        current_overview_version=state.current_overview_version,
        satisfied_state_afters=state.satisfied_state_afters,
        current_guide_decision_ids={item.decision_id for item in decisions},
        current_guide_check_ids={item.check_id for item in checks},
    )
    results = [AcceptanceEvaluationResult(kind=phase_result.kind.value, reason=phase_result.reason)]
    module_result = None
    experiment_result = None
    if phase_result.kind == PhaseGateKind.PHASE_DONE:
        current_phase.status = PhaseStatus.DONE
        if current_phase.state_after:
            state.satisfied_state_afters.add(current_phase.state_after)
        module_phases = [phase for phase in state.phases if phase.module_id == current_module.module_id]
        phase_results = [
            phase_result if phase.phase_id == current_phase.phase_id else AcceptanceEvaluationResult(kind="keep_current_state")
            for phase in module_phases
        ]
        module_result = evaluate_module_gate(
            current_module,
            phases=module_phases,
            phase_results=phase_results,  # type: ignore[arg-type]
            decision_items=decisions,
            done_checks=checks,
            current_overview_version=state.current_overview_version,
        )
        results.append(AcceptanceEvaluationResult(kind=module_result.kind.value, reason=module_result.reason))
        if module_result.kind == ModuleGateKind.MODULE_DONE:
            experiment_result = evaluate_experiment_gate(
                modules=state.modules,
                module_results=[module_result],
                decision_items=decisions,
                done_checks=checks,
                current_overview_version=state.current_overview_version,
            )
            results.append(AcceptanceEvaluationResult(kind=experiment_result.kind.value, reason=experiment_result.reason))

    if current_guide is not None:
        for candidate in state.adopted_results:
            evaluation = evaluate_adoption_candidate(
                candidate,
                source_decisions=decisions,
                source_done_checks=checks,
                source_records=state.action_records,
                current_overview_version=state.current_overview_version,
                phase_gate_result=phase_result,
                module_gate_result=module_result,
                experiment_gate_result=experiment_result,
            )
            if evaluation.kind == AdoptionEvaluationKind.ADOPTED:
                results.append(AcceptanceEvaluationResult(kind="adopted", adopted_item=evaluation.adopted_item))
    return results


def handle_acceptance_result(state: RuntimeState, result: AcceptanceEvaluationResult) -> str:
    if result.kind == "keep_current_state":
        return "continue_loop"
    if result.kind == "revise_guide":
        state.current_guide_id = None
        state.current_action_id = None
        return "continue_loop"
    if result.kind == "pause_acceptance":
        state.runtime_status = RuntimeStatus.PAUSED
        return "terminal"
    if result.kind == "escalate_to_overview_revision":
        return "migrate"
    if result.kind in {"phase_done", "module_done"}:
        return "continue_loop"
    if result.kind == "experiment_done":
        state.runtime_status = RuntimeStatus.COMPLETED
        return "terminal"
    if result.kind == "adopted":
        if result.adopted_item is not None:
            state.adopted_results.append(result.adopted_item)
        return "continue_loop"
    raise ValueError(f"unsupported acceptance result: {result.kind}")


def handle_acceptance_results(state: RuntimeState, results: list[AcceptanceEvaluationResult]) -> str:
    outcome = "continue_loop"
    for result in results:
        handled = handle_acceptance_result(state, result)
        if handled in {"terminal", "migrate"}:
            return handled
        outcome = handled
    return outcome


def old_guides_inactive_after_migration(state: RuntimeState, old_guide_ids: set[str]) -> bool:
    return all(guide.guide_id not in old_guide_ids for guide in state.guides)
