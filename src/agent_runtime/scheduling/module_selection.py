"""Module-layer validation and selection."""

from __future__ import annotations

from agent_runtime.models import ModuleStatus

from .helpers import (
    SKELETON_DEFECT_REASONS,
    contains_reason,
    dependency_satisfied,
    has_phase_candidate,
    module_is_waiting_blocked,
    ordered_modules,
)
from .result_types import ModuleResolution, ModuleResolutionKind, SchedulerRuntimeState


def validate_current_module(state: SchedulerRuntimeState) -> ModuleResolution:
    overview_version = state.inventory.experiment_overview.version
    current = next((module for module in state.inventory.modules if module.module_id == state.current_module_id), None)
    if current is None:
        return select_module(state)
    if current.overview_version != overview_version:
        return ModuleResolution(
            kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION,
            module_id=current.module_id,
            reason="version_mismatch",
        )
    if current.status == ModuleStatus.FAILED:
        defect_reason = contains_reason(current.failure_reasons, SKELETON_DEFECT_REASONS)
        if defect_reason is not None:
            return ModuleResolution(
                kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION,
                module_id=current.module_id,
                reason=defect_reason,
            )
    if current.status in {ModuleStatus.OBSOLETE, ModuleStatus.DONE}:
        return select_module(state)
    if current.status == ModuleStatus.BLOCKED:
        alternatives = _selectable_alternatives(state, exclude_module_id=current.module_id)
        if alternatives:
            return ModuleResolution(
                kind=ModuleResolutionKind.SWITCH_MODULE,
                module_id=alternatives[0].module_id,
                reason="blocked_with_alternative",
            )
        if module_is_waiting_blocked(state, current):
            return ModuleResolution(
                kind=ModuleResolutionKind.PAUSE_MODULE,
                module_id=current.module_id,
                reason="only_waiting_module",
            )
        return ModuleResolution(
            kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION,
            module_id=current.module_id,
            reason="non_waiting_blocked_module",
        )
    if not dependency_satisfied(state, current):
        return select_module(state)
    if not has_phase_candidate(state, current):
        return select_module(state)
    return ModuleResolution(kind=ModuleResolutionKind.KEEP_CURRENT_MODULE, module_id=current.module_id)


def select_module(state: SchedulerRuntimeState) -> ModuleResolution:
    candidates = _selectable_alternatives(state, exclude_module_id=None)
    if candidates:
        return ModuleResolution(kind=ModuleResolutionKind.SWITCH_MODULE, module_id=candidates[0].module_id)

    blocked_candidates = [
        module
        for module in ordered_modules(state)
        if module.overview_version == state.inventory.experiment_overview.version and module.status == ModuleStatus.BLOCKED
    ]
    waiting_blocked_candidates = [module for module in blocked_candidates if module_is_waiting_blocked(state, module)]
    if waiting_blocked_candidates:
        return ModuleResolution(
            kind=ModuleResolutionKind.PAUSE_MODULE,
            module_id=waiting_blocked_candidates[0].module_id,
            reason="only_waiting_module",
        )
    return ModuleResolution(
        kind=ModuleResolutionKind.ESCALATE_MODULE_TO_OVERVIEW_REVISION,
        reason="no_legal_module",
    )


def _selectable_alternatives(state: SchedulerRuntimeState, exclude_module_id: str | None) -> list:
    selectable = []
    for module in ordered_modules(state):
        if exclude_module_id is not None and module.module_id == exclude_module_id:
            continue
        if module.overview_version != state.inventory.experiment_overview.version:
            continue
        if module.status in {ModuleStatus.BLOCKED, ModuleStatus.DONE, ModuleStatus.FAILED, ModuleStatus.OBSOLETE}:
            continue
        if not dependency_satisfied(state, module):
            continue
        if not has_phase_candidate(state, module):
            continue
        selectable.append(module)
    return selectable
