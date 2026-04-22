"""Typed result objects for Phase 3 scheduling."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent_runtime.models import ObjectInventory
from agent_runtime.models.common import ModelBase


class ModuleResolutionKind(StrEnum):
    KEEP_CURRENT_MODULE = "keep_current_module"
    SWITCH_MODULE = "switch_module"
    PAUSE_MODULE = "pause_module"
    ESCALATE_MODULE_TO_OVERVIEW_REVISION = "escalate_module_to_overview_revision"


class PhaseResolutionKind(StrEnum):
    KEEP_CURRENT_PHASE = "keep_current_phase"
    SWITCH_PHASE = "switch_phase"
    PAUSE_WAIT_EXTERNAL_TOOL_RESULT = "pause_wait_external_tool_result"
    PAUSE_WAIT_HUMAN_INPUT = "pause_wait_human_input"
    PAUSE_WAIT_EXTERNAL_RESOURCE = "pause_wait_external_resource"
    REVISE_GUIDE_KEEP_PHASE = "revise_guide_keep_phase"
    ESCALATE_TO_OVERVIEW_REVISION = "escalate_to_overview_revision"


class GuideResolutionKind(StrEnum):
    USE_GUIDE = "use_guide"
    REVISE_GUIDE_KEEP_PHASE = "revise_guide_keep_phase"
    ESCALATE_TO_OVERVIEW_REVISION = "escalate_to_overview_revision"


class ActionResolutionKind(StrEnum):
    CONTINUE_CURRENT_ACTION = "continue_current_action"
    RETRY_CURRENT_ACTION = "retry_current_action"
    ABANDON_CURRENT_ACTION_AND_SWITCH = "abandon_current_action_and_switch"
    PAUSE_WAIT_EXTERNAL_TOOL_RESULT = "pause_wait_external_tool_result"
    PAUSE_WAIT_HUMAN_INPUT = "pause_wait_human_input"
    PAUSE_WAIT_EXTERNAL_RESOURCE = "pause_wait_external_resource"
    REVISE_GUIDE_KEEP_PHASE = "revise_guide_keep_phase"
    ESCALATE_TO_OVERVIEW_REVISION = "escalate_to_overview_revision"
    NO_EXECUTABLE_ACTION_PAUSE = "no_executable_action_pause"
    NO_EXECUTABLE_ACTION_REVISE_GUIDE = "no_executable_action_revise_guide"
    NO_EXECUTABLE_ACTION_ESCALATE = "no_executable_action_escalate"


class SchedulerRuntimeState(ModelBase):
    """Minimal runtime context consumed by the Phase 3 scheduler."""

    inventory: ObjectInventory
    current_module_id: str | None = None
    current_phase_id: str | None = None
    current_action_id: str | None = None
    satisfied_state_afters: set[str] = Field(default_factory=set)
    locally_repairable_phase_ids: set[str] = Field(default_factory=set)
    useful_returned_action_ids: set[str] = Field(default_factory=set)


class ModuleResolution(ModelBase):
    kind: ModuleResolutionKind
    module_id: str | None = None
    reason: str | None = None


class PhaseResolution(ModelBase):
    kind: PhaseResolutionKind
    phase_id: str | None = None
    reason: str | None = None


class GuideResolution(ModelBase):
    kind: GuideResolutionKind
    guide_id: str | None = None
    reason: str | None = None


class ActionResolution(ModelBase):
    kind: ActionResolutionKind
    action_id: str | None = None
    guide_id: str | None = None
    reason: str | None = None
