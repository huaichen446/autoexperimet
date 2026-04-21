"""Shared model helpers and enums for typed runtime schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ModelBase(BaseModel):
    """Repository-standard Pydantic base model for typed, explicit schemas."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class DecompositionFeasibility(StrEnum):
    MULTI_MODULE = "multi_module"
    SINGLE_MODULE = "single_module"
    UNDECIDED = "undecided"


class AuditStatus(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ModuleStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    OBSOLETE = "obsolete"


class PhaseStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"
    OBSOLETE = "obsolete"


class ActionType(StrEnum):
    AUTO = "auto"
    EXTERNAL_TOOL = "external_tool"
    HUMAN_INPUT = "human_input"


class ActionRecordStatus(StrEnum):
    SELECTED = "selected"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    DONE = "done"
    ABANDONED = "abandoned"


class GuideStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    CLOSED = "closed"


class DecisionStatus(StrEnum):
    OPEN = "open"
    DECIDED = "decided"
    BLOCKED = "blocked"
    OBSOLETE = "obsolete"


class DoneCheckStatus(StrEnum):
    UNMET = "unmet"
    MET = "met"
    BLOCKED = "blocked"


class ActionStatus(StrEnum):
    PENDING = "pending"
    SELECTED = "selected"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    DONE = "done"
    ABANDONED = "abandoned"
    SKIPPED = "skipped"


class ActionExecutorHint(StrEnum):
    AGENT = "agent"
    TOOL = "tool"
    HUMAN = "human"
