"""Runtime-layer models that bind directly to skeleton overviews."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import ActionRecordStatus, ActionType, ModelBase, ModuleStatus, PhaseStatus


class Module(ModelBase):
    """Runtime module instance bound to one module overview within one overview version."""

    module_id: str
    experiment_id: str
    overview_version: int = Field(ge=1)
    module_overview_ref: str

    name: str
    goal: str

    phase_ids: list[str] = Field(min_length=1)
    current_phase_id: str | None = None
    completed_phase_ids: list[str] = Field(default_factory=list)
    blocked_phase_ids: list[str] = Field(default_factory=list)

    status: ModuleStatus
    notes: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    retry_history: list[str] = Field(default_factory=list)

    needs_redecomposition: bool = False

    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_runtime_state(self) -> "Module":
        if not self.module_id:
            raise ValueError("module_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.module_overview_ref:
            raise ValueError("module_overview_ref must be present")
        if len(set(self.phase_ids)) != len(self.phase_ids):
            raise ValueError("phase_ids must be unique within a module")
        if self.current_phase_id and self.current_phase_id not in self.phase_ids:
            raise ValueError("current_phase_id must be present in phase_ids")
        if not set(self.completed_phase_ids).issubset(set(self.phase_ids)):
            raise ValueError("completed_phase_ids must be a subset of phase_ids")
        if not set(self.blocked_phase_ids).issubset(set(self.phase_ids)):
            raise ValueError("blocked_phase_ids must be a subset of phase_ids")
        if self.status == ModuleStatus.BLOCKED and not self.blocked_phase_ids:
            raise ValueError("blocked modules must identify blocked_phase_ids")
        if self.status == ModuleStatus.FAILED and not self.failure_reasons:
            raise ValueError("failed modules must include failure_reasons")
        return self


class Phase(ModelBase):
    """Runtime phase instance bound to one phase overview within one overview version."""

    phase_id: str
    module_id: str
    experiment_id: str
    overview_version: int = Field(ge=1)
    phase_overview_ref: str

    name: str
    role: str
    state_after: str

    status: PhaseStatus
    is_expanded: bool = False
    notes: list[str] = Field(default_factory=list)

    failure_reasons: list[str] = Field(default_factory=list)
    retry_history: list[str] = Field(default_factory=list)

    fallback_boundary: str

    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_runtime_state(self) -> "Phase":
        if not self.phase_id:
            raise ValueError("phase_id must be present")
        if not self.module_id:
            raise ValueError("module_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.phase_overview_ref:
            raise ValueError("phase_overview_ref must be present")
        if not self.fallback_boundary:
            raise ValueError("fallback_boundary must be present")
        if self.status == PhaseStatus.BLOCKED and not self.failure_reasons:
            raise ValueError("blocked phases must include failure_reasons")
        if self.status == PhaseStatus.FAILED and not self.failure_reasons:
            raise ValueError("failed phases must include failure_reasons")
        return self


class ActionRecord(ModelBase):
    """Single-attempt runtime record linked to one action inside one execution guide."""

    action_record_id: str
    experiment_id: str
    module_id: str
    phase_id: str

    overview_version: int = Field(ge=1)
    guide_id: str
    action_id: str

    action_type: ActionType
    executor: str
    status: ActionRecordStatus

    input_snapshot: dict = Field(default_factory=dict)
    output_snapshot: dict | None = None
    result_summary: str
    evidence_refs: list[str] = Field(default_factory=list)

    failure_reason: str | None = None
    retry_index: int = Field(ge=0)

    started_at: str | None = None
    finished_at: str | None = None
    created_at: str

    @model_validator(mode="after")
    def validate_single_attempt_state(self) -> "ActionRecord":
        if not self.action_record_id:
            raise ValueError("action_record_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.module_id:
            raise ValueError("module_id must be present")
        if not self.phase_id:
            raise ValueError("phase_id must be present")
        if not self.guide_id:
            raise ValueError("guide_id must be present")
        if not self.action_id:
            raise ValueError("action_id must be present")

        if self.status == ActionRecordStatus.PLANNED:
            if self.started_at or self.finished_at:
                raise ValueError("planned action records cannot include started_at or finished_at")
        elif self.status == ActionRecordStatus.RUNNING:
            if not self.started_at:
                raise ValueError("running action records must include started_at")
            if self.finished_at:
                raise ValueError("running action records cannot include finished_at")
        else:
            if not self.started_at:
                raise ValueError("terminal action records must include started_at")
            if not self.finished_at:
                raise ValueError("terminal action records must include finished_at")

        if self.status == ActionRecordStatus.SUCCEEDED and self.output_snapshot is None:
            raise ValueError("succeeded action records must include output_snapshot")
        if self.status in {ActionRecordStatus.FAILED, ActionRecordStatus.BLOCKED} and not self.failure_reason:
            raise ValueError("failed or blocked action records must include failure_reason")
        return self
