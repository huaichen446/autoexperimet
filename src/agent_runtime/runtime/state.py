"""Phase 6 runtime state objects."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from agent_runtime.models import ActionRecord, AdoptedDesignItem, ExecutionGuide, ExperimentOverview, Module, Phase
from agent_runtime.models.common import ModelBase


class RuntimeStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PAUSED = "paused"
    ESCALATED = "escalated"


class RuntimeState(ModelBase):
    """Small top-level runtime state for deterministic Phase 6 orchestration."""

    overview: ExperimentOverview
    modules: list[Module] = Field(default_factory=list)
    phases: list[Phase] = Field(default_factory=list)
    guides: list[ExecutionGuide] = Field(default_factory=list)
    action_records: list[ActionRecord] = Field(default_factory=list)

    current_overview_version: int = Field(ge=1)
    current_module_id: str | None = None
    current_phase_id: str | None = None
    current_guide_id: str | None = None
    current_action_id: str | None = None
    runtime_status: RuntimeStatus = RuntimeStatus.IN_PROGRESS

    satisfied_state_afters: set[str] = Field(default_factory=set)
    locally_repairable_phase_ids: set[str] = Field(default_factory=set)
    useful_returned_action_ids: set[str] = Field(default_factory=set)
    waiting_context: dict | None = None
    issue_evidence: list[str] = Field(default_factory=list)
    adopted_results: list[AdoptedDesignItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_and_version(self) -> "RuntimeState":
        if self.runtime_status not in {
            RuntimeStatus.IN_PROGRESS,
            RuntimeStatus.COMPLETED,
            RuntimeStatus.PAUSED,
            RuntimeStatus.ESCALATED,
        }:
            raise ValueError("unsupported runtime_status")
        return self


def initialize_runtime_state(
    *,
    overview: ExperimentOverview,
    modules: list[Module],
    phases: list[Phase],
    guides: list[ExecutionGuide] | None = None,
    action_records: list[ActionRecord] | None = None,
) -> RuntimeState:
    return RuntimeState(
        overview=overview,
        modules=modules,
        phases=phases,
        guides=guides or [],
        action_records=action_records or [],
        current_overview_version=overview.version,
        current_module_id=None,
        current_phase_id=None,
        current_guide_id=None,
        current_action_id=None,
        runtime_status=RuntimeStatus.IN_PROGRESS,
    )


def is_terminal_status(status: RuntimeStatus) -> bool:
    return status in {RuntimeStatus.COMPLETED, RuntimeStatus.PAUSED, RuntimeStatus.ESCALATED}
