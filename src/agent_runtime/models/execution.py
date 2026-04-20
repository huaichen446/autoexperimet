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


class DecisionItem(ModelBase):
    """A single unresolved, decided, blocked, or obsolete decision inside a guide."""

    decision_id: str
    question: str
    status: DecisionStatus
    decision: str | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "DecisionItem":
        if not self.decision_id:
            raise ValueError("decision_id must be present")
        if self.status == DecisionStatus.DECIDED:
            if not self.decision:
                raise ValueError("decided decision items must include decision")
            if not self.rationale:
                raise ValueError("decided decision items must include rationale")
        if self.status == DecisionStatus.BLOCKED and not self.rationale:
            raise ValueError("blocked decision items must include rationale")
        return self


class DoneCheck(ModelBase):
    """A minimal done criterion attached to one execution guide."""

    check_id: str
    description: str
    status: DoneCheckStatus
    evidence_ref: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "DoneCheck":
        if not self.check_id:
            raise ValueError("check_id must be present")
        if self.status == DoneCheckStatus.MET and not self.evidence_ref:
            raise ValueError("met done checks must include evidence_ref")
        return self


class Action(ModelBase):
    """A guide-scoped action definition.

    The ``status`` field is a mirror/cache field for the guide's current view of
    action progress. It is intentionally schema-only in Phase 1 and does not
    implement execution behavior.
    """

    action_id: str
    title: str
    action_type: ActionType
    executor_hint: ActionExecutorHint
    instruction: str
    expected_output: str
    status: ActionStatus = ActionStatus.PENDING

    @model_validator(mode="after")
    def validate_state(self) -> "Action":
        if not self.action_id:
            raise ValueError("action_id must be present")
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
