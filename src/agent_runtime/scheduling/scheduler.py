"""Top-level scheduler entry point for Phase 3."""

from __future__ import annotations

from agent_runtime.models import ExecutionGuide

from .action_resolution import resolve_current_action
from .guide_resolution import resolve_current_active_guide
from .module_selection import validate_current_module
from .phase_selection import validate_current_phase
from .result_types import ActionResolution, GuideResolutionKind, ModuleResolutionKind, PhaseResolutionKind, SchedulerRuntimeState


def schedule_runtime(state: SchedulerRuntimeState):
    module_resolution = validate_current_module(state)
    if module_resolution.kind != ModuleResolutionKind.KEEP_CURRENT_MODULE:
        return module_resolution
    phase_resolution = validate_current_phase(state)
    if phase_resolution.kind != PhaseResolutionKind.KEEP_CURRENT_PHASE:
        return phase_resolution
    guide_resolution = resolve_current_active_guide(state)
    if guide_resolution.kind != GuideResolutionKind.USE_GUIDE:
        return guide_resolution
    guide = next(guide for guide in state.inventory.guides if guide.guide_id == guide_resolution.guide_id)
    return resolve_current_action(state, guide)
