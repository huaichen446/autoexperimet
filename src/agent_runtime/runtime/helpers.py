"""Small helpers shared by Phase 6 runtime orchestration."""

from __future__ import annotations

from agent_runtime.migration import build_phases_from_overview
from agent_runtime.models import ExperimentOverview, Module, ModuleStatus, ObjectInventory

from .results import OverviewValidityKind, OverviewValidityResult, RuntimeResult, RuntimeResultKind
from .state import RuntimeState, RuntimeStatus


def build_initial_modules_from_overview(overview: ExperimentOverview) -> list[Module]:
    modules: list[Module] = []
    for module_overview in sorted(overview.modules, key=lambda item: (item.sort_index, item.module_overview_id)):
        modules.append(
            Module(
                module_id=module_overview.module_overview_id,
                experiment_id=overview.experiment_id,
                overview_version=overview.version,
                module_overview_ref=module_overview.module_overview_id,
                name=module_overview.name,
                goal=module_overview.goal,
                phase_ids=[
                    phase.phase_overview_id
                    for phase in sorted(module_overview.phase_overviews, key=lambda item: (item.sort_index, item.phase_overview_id))
                ],
                current_phase_id=None,
                completed_phase_ids=[],
                blocked_phase_ids=[],
                status=ModuleStatus.NOT_STARTED,
                notes=[],
                failure_reasons=[],
                retry_history=[],
                needs_redecomposition=False,
                created_at=overview.created_at,
                updated_at=overview.created_at,
            )
        )
    return modules


def build_initial_runtime_objects(overview: ExperimentOverview) -> tuple[list[Module], list]:
    return build_initial_modules_from_overview(overview), build_phases_from_overview(overview)


def build_inventory(state: RuntimeState) -> ObjectInventory:
    return ObjectInventory(
        experiment_overview=state.overview,
        modules=state.modules,
        phases=state.phases,
        guides=state.guides,
        action_records=state.action_records,
        main_doc=None,
    )


def validate_current_overview_version(state: RuntimeState) -> OverviewValidityResult:
    if state.overview.version != state.current_overview_version:
        return OverviewValidityResult(kind=OverviewValidityKind.INVALID, reason="overview_version_pointer_mismatch")
    if state.overview.superseded_by_version is not None:
        return OverviewValidityResult(kind=OverviewValidityKind.INVALID, reason="overview_superseded")
    if any(module.overview_version != state.current_overview_version for module in state.modules):
        return OverviewValidityResult(kind=OverviewValidityKind.INVALID, reason="module_version_mismatch")
    if any(phase.overview_version != state.current_overview_version for phase in state.phases):
        return OverviewValidityResult(kind=OverviewValidityKind.INVALID, reason="phase_version_mismatch")
    if any(guide.overview_version != state.current_overview_version for guide in state.guides):
        return OverviewValidityResult(kind=OverviewValidityKind.INVALID, reason="guide_version_mismatch")
    if any(record.overview_version != state.current_overview_version for record in state.action_records):
        return OverviewValidityResult(kind=OverviewValidityKind.INVALID, reason="action_record_version_mismatch")
    return OverviewValidityResult(kind=OverviewValidityKind.VALID)


def finalize_runtime_result(state: RuntimeState, *, reason: str | None = None) -> RuntimeResult:
    if state.runtime_status == RuntimeStatus.COMPLETED:
        return RuntimeResult(kind=RuntimeResultKind.COMPLETED, state=state, reason=reason)
    if state.runtime_status == RuntimeStatus.PAUSED:
        return RuntimeResult(kind=RuntimeResultKind.PAUSED, state=state, reason=reason)
    if state.runtime_status == RuntimeStatus.ESCALATED:
        return RuntimeResult(kind=RuntimeResultKind.ESCALATED, state=state, reason=reason)
    raise ValueError("cannot finalize a non-terminal runtime state")
