"""Runtime-layer models that bind directly to skeleton overviews."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import (
    ActionRecordStatus,
    ActionType,
    ModelBase,
    ModuleStatus,
    PhaseStatus,
)


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


class RequiredInput(ModelBase):
    """A typed runtime input requirement declared by an action."""

    input_key: str
    source_type: str
    required: bool
    value_type: str
    materialization_stage: str

    @model_validator(mode="after")
    def validate_shape(self) -> "RequiredInput":
        if not self.input_key:
            raise ValueError("input_key must be present")
        if self.source_type not in {
            "guide",
            "runtime_context",
            "external_tool",
            "human_input",
            "external_resource",
        }:
            raise ValueError("source_type is not supported")
        if self.value_type not in {"str", "json", "table", "artifact_ref", "enum", "bool", "number"}:
            raise ValueError("value_type is not supported")
        if self.materialization_stage not in {"pre_select", "pre_run", "post_wait_resume"}:
            raise ValueError("materialization_stage is not supported")
        return self


class FailureReason(ModelBase):
    """Structured failure state for a single action attempt."""

    category: str
    code: str
    message: str
    retryable: bool
    counts_as_retry: bool

    @model_validator(mode="after")
    def validate_shape(self) -> "FailureReason":
        if self.category not in {
            "transient_failure",
            "permanent_failure",
            "capability_mismatch",
            "invalid_input",
            "policy_blocked",
            "dependency_missing",
        }:
            raise ValueError("failure category is not supported")
        if not self.code:
            raise ValueError("failure code must be present")
        if not self.message:
            raise ValueError("failure message must be present")
        return self


class BlockedReason(ModelBase):
    """Structured blocked state for a single action attempt."""

    blocked_reason_type: str
    code: str
    message: str
    retryable_after_unblock: bool

    @model_validator(mode="after")
    def validate_shape(self) -> "BlockedReason":
        if self.blocked_reason_type not in {
            "external_tool_not_ready",
            "human_input_missing",
            "external_resource_not_ready",
            "guide_missing_info",
            "undeclared_dependency",
            "fallback_boundary_violation",
        }:
            raise ValueError("blocked_reason_type is not supported")
        if not self.code:
            raise ValueError("blocked code must be present")
        if not self.message:
            raise ValueError("blocked message must be present")
        return self


class WaitingTarget(ModelBase):
    """An explicit waiting target for resumable blocked attempts."""

    waiting_type: str
    target_id: str
    correlation_key: str

    @model_validator(mode="after")
    def validate_shape(self) -> "WaitingTarget":
        if self.waiting_type not in {"external_tool", "human", "external_resource"}:
            raise ValueError("waiting_type is not supported")
        if not self.target_id:
            raise ValueError("target_id must be present")
        if not self.correlation_key:
            raise ValueError("correlation_key must be present")
        return self


class ExternalCorrelationKey(ModelBase):
    """Correlates outbound requests with later async arrivals."""

    correlation_type: str
    correlation_key: str

    @model_validator(mode="after")
    def validate_shape(self) -> "ExternalCorrelationKey":
        if self.correlation_type not in {"external_tool_request", "human_request"}:
            raise ValueError("correlation_type is not supported")
        if not self.correlation_key:
            raise ValueError("correlation_key must be present")
        return self


class ActionRecord(ModelBase):
    """Single-attempt mutable runtime record linked to one action."""

    action_record_id: str
    experiment_id: str
    module_id: str
    phase_id: str
    guide_id: str
    action_id: str
    overview_version: int = Field(ge=1)

    attempt_index: int = Field(ge=1)
    parent_attempt_index: int | None = Field(default=None, ge=1)

    action_type: ActionType
    executor_type: str

    attempt_status: ActionRecordStatus
    finalized: bool
    record_integrity: str

    input_snapshot: dict = Field(default_factory=dict)
    execution_payload: dict | None = None
    output_snapshot: dict | None = None
    result_summary: dict | None = None

    failure_reason: FailureReason | None = None
    blocked_reason: BlockedReason | None = None
    waiting_target: WaitingTarget | None = None

    tool_request: dict | None = None
    tool_response: dict | None = None
    tool_call_status: str | None = None

    request_target: dict | None = None
    request_payload: dict | None = None
    returned_input: dict | None = None

    evidence_refs: list[str] = Field(default_factory=list)
    phase_writeback_hint: str
    counts_as_retry: bool

    selected_at: str
    started_at: str | None = None
    terminal_at: str | None = None
    created_at: str
    finalized_at: str | None = None

    external_correlation_key: ExternalCorrelationKey | None = None

    record_revision: int = Field(ge=1)
    mutation_reason_code: str
    mutation_log_required: bool

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
        if self.record_integrity not in {"valid", "invalid", "repaired"}:
            raise ValueError("record_integrity must be valid, invalid, or repaired")
        if self.phase_writeback_hint not in {"notes_only", "in_progress", "blocked", "failed", "done"}:
            raise ValueError("phase_writeback_hint is not supported")
        if not self.selected_at:
            raise ValueError("selected_at must be present")
        if not self.created_at:
            raise ValueError("created_at must be present")
        if not self.mutation_reason_code:
            raise ValueError("mutation_reason_code must be present")
        if self.finalized and not self.finalized_at:
            raise ValueError("finalized action records must include finalized_at")
        if self.attempt_status == ActionRecordStatus.BLOCKED and self.blocked_reason is None:
            raise ValueError("blocked action records must include blocked_reason")
        if (
            self.attempt_status == ActionRecordStatus.BLOCKED
            and self.blocked_reason is not None
            and self.blocked_reason.blocked_reason_type
            in {
                "external_tool_not_ready",
                "human_input_missing",
                "external_resource_not_ready",
            }
            and self.waiting_target is None
        ):
            raise ValueError("resumable blocked action records must include waiting_target")
        if self.attempt_status == ActionRecordStatus.FAILED and self.failure_reason is None:
            raise ValueError("failed action records must include failure_reason")
        if self.attempt_status == ActionRecordStatus.DONE and self.output_snapshot is None:
            raise ValueError("done action records must include output_snapshot")
        if self.attempt_status in {
            ActionRecordStatus.RUNNING,
            ActionRecordStatus.FAILED,
            ActionRecordStatus.DONE,
        } and self.started_at is None:
            raise ValueError("running, failed, and done action records must include started_at")
        if self.attempt_status in {
            ActionRecordStatus.FAILED,
            ActionRecordStatus.DONE,
            ActionRecordStatus.ABANDONED,
        } and self.terminal_at is None:
            raise ValueError("terminal action records must include terminal_at")
        if self.attempt_status in {
            ActionRecordStatus.SELECTED,
            ActionRecordStatus.RUNNING,
            ActionRecordStatus.BLOCKED,
        } and self.terminal_at is not None:
            raise ValueError("active action records cannot include terminal_at")
        if self.attempt_status == ActionRecordStatus.ABANDONED and self.phase_writeback_hint != "notes_only":
            raise ValueError("abandoned action records must use notes_only phase_writeback_hint")
        return self
