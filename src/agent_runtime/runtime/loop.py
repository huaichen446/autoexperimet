"""Top-level deterministic Phase 6 runtime loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agent_runtime.models import ExperimentOverview
from agent_runtime.scheduling import (
    SchedulerRuntimeState,
    resolve_current_action,
    resolve_current_active_guide,
    validate_current_module,
    validate_current_phase,
)

from .helpers import build_initial_runtime_objects, build_inventory, finalize_runtime_result, validate_current_overview_version
from .orchestration import (
    apply_migration_result,
    evaluate_acceptance_and_promotion,
    handle_acceptance_results,
    handle_action_result,
    handle_execution_writeback,
    handle_guide_result,
    handle_module_result,
    handle_phase_result,
    resolve_bound_current_guide,
    run_overview_revision_and_migration,
)
from .results import AcceptanceEvaluationResult, ExecutionWritebackResult, OverviewValidityKind, RuntimeResult
from .state import RuntimeState, RuntimeStatus, initialize_runtime_state, is_terminal_status


@dataclass
class RuntimeServices:
    resolve_module: Callable[[SchedulerRuntimeState], object] = validate_current_module
    resolve_phase: Callable[[SchedulerRuntimeState], object] = validate_current_phase
    resolve_guide: Callable[[SchedulerRuntimeState], object] = resolve_current_active_guide
    resolve_action: Callable[[SchedulerRuntimeState, object], object] = resolve_current_action
    execute_action: Callable[[RuntimeState], ExecutionWritebackResult | None] | None = None
    evaluate_acceptance: Callable[[RuntimeState], list[AcceptanceEvaluationResult]] = evaluate_acceptance_and_promotion
    run_migration: Callable[[RuntimeState], object] | None = None
    trace: Callable[[str], None] | None = None


def run_experiment_runtime(
    *,
    experiment_input: object | None = None,
    overview: ExperimentOverview | None = None,
    overview_factory: Callable[[object | None], ExperimentOverview] | None = None,
    services: RuntimeServices | None = None,
    max_iterations: int = 100,
) -> RuntimeResult:
    if overview is None:
        if overview_factory is None:
            raise ValueError("overview or overview_factory is required")
        overview = overview_factory(experiment_input)
    modules, phases = build_initial_runtime_objects(overview)
    state = initialize_runtime_state(overview=overview, modules=modules, phases=phases)
    return run_runtime(state=state, services=services, max_iterations=max_iterations)


def run_runtime(
    *,
    state: RuntimeState,
    services: RuntimeServices | None = None,
    max_iterations: int = 100,
) -> RuntimeResult:
    services = services or RuntimeServices()
    reason: str | None = None

    for _ in range(max_iterations):
        _trace(services, "terminal_check")
        if is_terminal_status(state.runtime_status):
            return finalize_runtime_result(state, reason=reason)

        _trace(services, "overview_validity")
        overview_validity = validate_current_overview_version(state)
        if overview_validity.kind == OverviewValidityKind.INVALID:
            reason = overview_validity.reason
            if not _run_migration_subflow(state, services):
                continue
            continue

        scheduler_state = _scheduler_state(state)

        _trace(services, "module_resolution")
        module_result = services.resolve_module(scheduler_state)  # type: ignore[arg-type]
        module_outcome = handle_module_result(state, module_result)  # type: ignore[arg-type]
        if module_outcome == "migrate":
            if not _run_migration_subflow(state, services):
                continue
            continue
        if module_outcome != "continue_stages":
            _trace(services, "terminal_recheck")
            continue

        scheduler_state = _scheduler_state(state)
        _trace(services, "phase_resolution")
        phase_result = services.resolve_phase(scheduler_state)  # type: ignore[arg-type]
        phase_outcome = handle_phase_result(state, phase_result)  # type: ignore[arg-type]
        if phase_outcome == "migrate":
            if not _run_migration_subflow(state, services):
                continue
            continue
        if phase_outcome != "continue_stages":
            _trace(services, "terminal_recheck")
            continue

        scheduler_state = _scheduler_state(state)
        _trace(services, "guide_resolution")
        guide_result = services.resolve_guide(scheduler_state)  # type: ignore[arg-type]
        guide_outcome = handle_guide_result(state, guide_result)  # type: ignore[arg-type]
        if guide_outcome == "migrate":
            if not _run_migration_subflow(state, services):
                continue
            continue
        if guide_outcome != "continue_stages":
            _trace(services, "terminal_recheck")
            continue

        guide = resolve_bound_current_guide(state)
        if guide is None:
            if not _run_migration_subflow(state, services):
                continue
            continue
        scheduler_state = _scheduler_state(state)
        _trace(services, "action_resolution")
        action_result = services.resolve_action(scheduler_state, guide)  # type: ignore[arg-type]
        action_outcome = handle_action_result(state, action_result)  # type: ignore[arg-type]
        if action_outcome == "migrate":
            if not _run_migration_subflow(state, services):
                continue
            continue
        if action_outcome != "execute":
            _trace(services, "terminal_recheck")
            continue

        _trace(services, "execution_writeback")
        execution_result = services.execute_action(state) if services.execute_action is not None else None
        execution_outcome = handle_execution_writeback(state, execution_result)
        if execution_outcome != "continue_stages":
            _trace(services, "terminal_recheck")
            continue

        _trace(services, "acceptance_promotion")
        acceptance_outcome = handle_acceptance_results(state, services.evaluate_acceptance(state))
        if acceptance_outcome == "migrate":
            if not _run_migration_subflow(state, services):
                continue
            continue

        _trace(services, "terminal_recheck")
        if is_terminal_status(state.runtime_status):
            return finalize_runtime_result(state, reason=reason)
        continue

    state.runtime_status = RuntimeStatus.ESCALATED
    return finalize_runtime_result(state, reason="runtime_iteration_limit_exceeded")


def _run_migration_subflow(state: RuntimeState, services: RuntimeServices) -> bool:
    _trace(services, "overview_revision_migration")
    migration_result = run_overview_revision_and_migration(state, migration_runner=services.run_migration)
    apply_migration_result(state, migration_result)
    return state.runtime_status == RuntimeStatus.IN_PROGRESS


def _scheduler_state(state: RuntimeState) -> SchedulerRuntimeState:
    return SchedulerRuntimeState(
        inventory=build_inventory(state),
        current_module_id=state.current_module_id,
        current_phase_id=state.current_phase_id,
        current_action_id=state.current_action_id,
        satisfied_state_afters=state.satisfied_state_afters,
        locally_repairable_phase_ids=state.locally_repairable_phase_ids,
        useful_returned_action_ids=state.useful_returned_action_ids,
    )


def _trace(services: RuntimeServices, stage: str) -> None:
    if services.trace is not None:
        services.trace(stage)
