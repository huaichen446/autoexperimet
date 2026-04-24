"""Phase 6 runtime result objects."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent_runtime.models import ExecutionGuide, ExperimentOverview, Module, Phase
from agent_runtime.models.common import ModelBase

from .state import RuntimeState, RuntimeStatus


class RuntimeResultKind(StrEnum):
    COMPLETED = "completed"
    PAUSED = "paused"
    ESCALATED = "escalated"


class OverviewValidityKind(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class OverviewValidityResult(ModelBase):
    kind: OverviewValidityKind
    reason: str | None = None


class RuntimeMigrationKind(StrEnum):
    AUTO_RESUMED = "auto_resumed"
    PAUSE_MIGRATION = "pause_migration"
    ESCALATE_MIGRATION = "escalate_migration"


class RuntimeMigrationResult(ModelBase):
    kind: RuntimeMigrationKind
    overview: ExperimentOverview | None = None
    modules: list[Module] = Field(default_factory=list)
    phases: list[Phase] = Field(default_factory=list)
    guides: list[ExecutionGuide] = Field(default_factory=list)
    resume_module_id: str | None = None
    resume_phase_id: str | None = None
    reason: str | None = None


class ExecutionWritebackResult(ModelBase):
    action_id: str | None = None
    action_records: list[object] | None = None
    clear_current_action: bool = False
    runtime_status: RuntimeStatus | None = None
    waiting_context: dict | None = None


class AcceptanceEvaluationResult(ModelBase):
    kind: str
    adopted_item: object | None = None
    reason: str | None = None


class RuntimeResult(ModelBase):
    kind: RuntimeResultKind
    state: RuntimeState
    reason: str | None = None

