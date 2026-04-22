"""Execution-control models for guide decisions, actions, and done checks."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import (
    ActionExecutorHint,
    ActionStatus,
    ActionType,
    DecisionStatus,
    DoneCheckStatus,
    GuideStatus,
    ModelBase,
)
from .runtime import BlockedReason, FailureReason, RequiredInput


class DecisionItem(ModelBase):
    """A structured decision required for phase/module/experiment acceptance."""

    decision_id: str
    experiment_id: str
    module_id: str | None = None
    phase_id: str | None = None
    guide_id: str | None = None
    overview_version: int = Field(ge=1)

    title: str
    decision_scope: str
    decision_type: str
    status: DecisionStatus

    required_for_phase_done: bool = False
    required_for_module_done: bool = False
    required_for_experiment_done: bool = False

    candidate_options: list[str] = Field(default_factory=list)
    selected_option: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    rationale_summary: str | None = None
    blocker_code: str | None = None
    blocker_detail: str | None = None

    created_at: str
    updated_at: str
    closed_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "title" not in data and "question" in data:
            data["title"] = data.pop("question")
        data.setdefault("decision_scope", "phase")
        data.setdefault("decision_type", "generic")
        data.setdefault("overview_version", 1)
        data.setdefault("created_at", "1970-01-01T00:00:00Z")
        data.setdefault("updated_at", data["created_at"])
        return data

    @model_validator(mode="after")
    def validate_state(self) -> "DecisionItem":
        if not self.decision_id:
            raise ValueError("decision_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.title:
            raise ValueError("title must be present")
        if self.decision_scope not in {"phase", "module", "experiment"}:
            raise ValueError("decision_scope is not supported")
        if not self.decision_type:
            raise ValueError("decision_type must be present")
        if not self.created_at:
            raise ValueError("created_at must be present")
        if not self.updated_at:
            raise ValueError("updated_at must be present")

        if self.decision_scope == "phase":
            if not self.module_id or not self.phase_id:
                raise ValueError("phase-scoped decisions must bind module_id and phase_id")
        elif self.decision_scope == "module":
            if not self.module_id:
                raise ValueError("module-scoped decisions must bind module_id")
            if self.phase_id is not None:
                raise ValueError("module-scoped decisions must not bind phase_id")
        elif self.module_id is not None or self.phase_id is not None:
            raise ValueError("experiment-scoped decisions must not bind module_id or phase_id")

        if self.status == DecisionStatus.DECIDED:
            if not self.selected_option:
                raise ValueError("decided decision items must include selected_option")
            if not self.evidence_refs:
                raise ValueError("decided decision items must include evidence_refs")
            if not self.rationale_summary:
                raise ValueError("decided decision items must include rationale_summary")
        if self.status == DecisionStatus.REJECTED:
            if not self.rationale_summary:
                raise ValueError("rejected decision items must include rationale_summary")
            if (
                (self.decision_scope == "phase" and self.required_for_phase_done)
                or (self.decision_scope == "module" and self.required_for_module_done)
                or (self.decision_scope == "experiment" and self.required_for_experiment_done)
            ):
                raise ValueError("rejected decision items cannot remain required for their current completion gate")
        if self.status == DecisionStatus.BLOCKED:
            if self.blocker_code not in {
                "waiting_external_tool",
                "waiting_human_input",
                "waiting_external_resource",
                "missing_evidence",
                "undeclared_dependency",
                "scope_conflict",
            }:
                raise ValueError("blocked decision items must include a supported blocker_code")
        return self


class DoneCheck(ModelBase):
    """A structured executable done criterion for acceptance gates."""

    check_id: str
    experiment_id: str
    module_id: str | None = None
    phase_id: str | None = None
    guide_id: str | None = None
    overview_version: int = Field(ge=1)

    check_scope: str
    title: str
    check_type: str
    status: DoneCheckStatus
    required: bool = True
    verifier_type: str | None = None
    verifier_config: dict = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    derived_from_action_ids: list[str] = Field(default_factory=list)
    derived_from_record_ids: list[str] = Field(default_factory=list)
    blocked_reason_code: str | None = None
    created_at: str
    updated_at: str
    met_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "title" not in data and "description" in data:
            data["title"] = data.pop("description")
        if "evidence_refs" not in data and "evidence_ref" in data:
            evidence_ref = data.pop("evidence_ref")
            data["evidence_refs"] = [] if evidence_ref is None else [evidence_ref]
        data.setdefault("check_scope", "phase")
        data.setdefault("check_type", "output_presence")
        data.setdefault("overview_version", 1)
        data.setdefault("created_at", "1970-01-01T00:00:00Z")
        data.setdefault("updated_at", data["created_at"])
        return data

    @model_validator(mode="after")
    def validate_state(self) -> "DoneCheck":
        if not self.check_id:
            raise ValueError("check_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.title:
            raise ValueError("title must be present")
        if self.check_scope not in {"phase", "module", "experiment"}:
            raise ValueError("check_scope is not supported")
        if self.check_type not in {
            "output_presence",
            "evidence_bound",
            "decision_closed",
            "threshold_met",
            "state_transition",
        }:
            raise ValueError("check_type is not supported")
        if not self.created_at:
            raise ValueError("created_at must be present")
        if not self.updated_at:
            raise ValueError("updated_at must be present")
        if self.status == DoneCheckStatus.BLOCKED and self.blocked_reason_code not in {
            "waiting_external_tool",
            "waiting_human_input",
            "waiting_external_resource",
            "missing_evidence",
            "missing_required_record",
            "scope_changed_by_migration",
        }:
            raise ValueError("blocked done checks must include a supported blocked_reason_code")
        return self


class Action(ModelBase):
    """A guide-scoped executable action with mirror-only runtime cache fields."""
    
    # identity / binding
    action_id: str
    experiment_id: str
    module_id: str
    phase_id: str
    guide_id: str
    overview_version: int = Field(ge=1)
    
    # guide-provided planning fields
    title: str
    action_type: ActionType
    executor_type: ActionExecutorHint
    instruction: str
    expected_output: str
    required_inputs: list[RequiredInput] = Field(default_factory=list)
    decision_item_refs: list[str] = Field(default_factory=list)
    done_check_refs: list[str] = Field(default_factory=list)
    expected_output_refs: list[str] = Field(default_factory=list)
    retry_policy: str
    max_retry: int = Field(ge=0)
    priority: int = 0
    declared_order: int = Field(ge=0)

    # runtime-materialized mirror-only fields
    status: ActionStatus | None = None
    current_attempt_index: int | None = Field(default=None, ge=1)
    retry_count: int | None = Field(default=None, ge=0)
    last_failure_reason: FailureReason | None = None
    last_blocked_reason: BlockedReason | None = None
    last_record_id: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "Action":
        if not self.action_id:
            raise ValueError("action_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.module_id:
            raise ValueError("module_id must be present")
        if not self.phase_id:
            raise ValueError("phase_id must be present")
        if not self.guide_id:
            raise ValueError("guide_id must be present")
        if self.retry_policy not in {"fixed", "none", "policy_override"}:
            raise ValueError("retry_policy must be fixed, none, or policy_override")
        for required_input in self.required_inputs:
            required_input.model_validate(required_input.model_dump())
        return self


class ExecutionGuide(ModelBase):
    """Guide bound to one runtime phase and module for a specific overview version."""

    guide_id: str
    experiment_id: str
    module_id: str
    phase_id: str
    overview_version: int = Field(ge=1)
    guide_version: int = Field(ge=1)
    status: GuideStatus

    phase_problem: str
    decision_items: list[DecisionItem] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    done_criteria: list[DoneCheck] = Field(default_factory=list)

    blockers: list[str] = Field(default_factory=list)
    fallback_rule: str
    notes: list[str] = Field(default_factory=list)

    created_from_phase_ref: str
    created_at: str
    superseded_by: str | None = None

    @model_validator(mode="after")
    def validate_bindings(self) -> "ExecutionGuide":
        if not self.guide_id:
            raise ValueError("guide_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.module_id:
            raise ValueError("module_id must be present")
        if not self.phase_id:
            raise ValueError("phase_id must be present")
        if not self.created_from_phase_ref:
            raise ValueError("created_from_phase_ref must be present")
        if self.created_from_phase_ref != self.phase_id:
            raise ValueError("created_from_phase_ref must match phase_id")
        if self.status == GuideStatus.SUPERSEDED and not self.superseded_by:
            raise ValueError("superseded guides must include superseded_by")

        decision_ids = [item.decision_id for item in self.decision_items]
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("decision_id values must be unique within an execution guide")

        action_ids = [action.action_id for action in self.actions]
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("action_id values must be unique within an execution guide")

        check_ids = [check.check_id for check in self.done_criteria]
        if len(set(check_ids)) != len(check_ids):
            raise ValueError("check_id values must be unique within an execution guide")
        return self
