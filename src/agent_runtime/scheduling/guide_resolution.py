"""Guide-layer resolution within the current phase."""

from __future__ import annotations

from agent_runtime.models import GuideStatus

from .helpers import phase_repairable_locally
from .result_types import GuideResolution, GuideResolutionKind, SchedulerRuntimeState


def resolve_current_active_guide(state: SchedulerRuntimeState) -> GuideResolution:
    if state.current_module_id is None or state.current_phase_id is None:
        return GuideResolution(kind=GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION, reason="missing_phase_or_module")
    overview_version = state.inventory.experiment_overview.version
    candidates = [
        guide
        for guide in state.inventory.guides
        if guide.module_id == state.current_module_id
        and guide.phase_id == state.current_phase_id
        and guide.overview_version == overview_version
        and guide.status == GuideStatus.ACTIVE
    ]
    if not candidates:
        if phase_repairable_locally(state, state.current_phase_id):
            return GuideResolution(
                kind=GuideResolutionKind.REVISE_GUIDE_KEEP_PHASE,
                reason="missing_guide",
            )
        return GuideResolution(
            kind=GuideResolutionKind.ESCALATE_TO_OVERVIEW_REVISION,
            reason="missing_guide",
        )

    selected = min(
        candidates,
        key=lambda guide: (-guide.guide_version, -_timestamp_rank(guide.created_at), guide.guide_id),
    )
    return GuideResolution(kind=GuideResolutionKind.USE_GUIDE, guide_id=selected.guide_id)


def _timestamp_rank(value: str) -> int:
    return int(value.replace("-", "").replace(":", "").replace("T", "").replace("Z", ""))
