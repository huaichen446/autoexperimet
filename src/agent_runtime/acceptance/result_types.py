"""Typed result objects for Phase 4 acceptance and promotion."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent_runtime.models.common import ModelBase


class AcceptanceRoute(StrEnum):
    KEEP_CURRENT_STATE = "keep_current_state"
    REVISE_GUIDE = "revise_guide"
    PAUSE_ACCEPTANCE = "pause_acceptance"
    ESCALATE_TO_OVERVIEW_REVISION = "escalate_to_overview_revision"


class PhaseGateKind(StrEnum):
    PHASE_DONE = "phase_done"
    KEEP_CURRENT_STATE = AcceptanceRoute.KEEP_CURRENT_STATE
    REVISE_GUIDE = AcceptanceRoute.REVISE_GUIDE
    PAUSE_ACCEPTANCE = AcceptanceRoute.PAUSE_ACCEPTANCE
    ESCALATE_TO_OVERVIEW_REVISION = AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION


class ModuleGateKind(StrEnum):
    MODULE_DONE = "module_done"
    KEEP_CURRENT_STATE = AcceptanceRoute.KEEP_CURRENT_STATE
    REVISE_GUIDE = AcceptanceRoute.REVISE_GUIDE
    PAUSE_ACCEPTANCE = AcceptanceRoute.PAUSE_ACCEPTANCE
    ESCALATE_TO_OVERVIEW_REVISION = AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION


class ExperimentGateKind(StrEnum):
    EXPERIMENT_DONE = "experiment_done"
    KEEP_CURRENT_STATE = AcceptanceRoute.KEEP_CURRENT_STATE
    PAUSE_ACCEPTANCE = AcceptanceRoute.PAUSE_ACCEPTANCE
    ESCALATE_TO_OVERVIEW_REVISION = AcceptanceRoute.ESCALATE_TO_OVERVIEW_REVISION


class AdoptionEvaluationKind(StrEnum):
    ADOPTED = "adopted"
    REJECTED = "rejected"


class PhaseGateResult(ModelBase):
    kind: PhaseGateKind
    reason: str | None = None
    missing_decision_ids: list[str] = Field(default_factory=list)
    missing_check_ids: list[str] = Field(default_factory=list)


class ModuleGateResult(ModelBase):
    kind: ModuleGateKind
    reason: str | None = None
    missing_phase_ids: list[str] = Field(default_factory=list)
    missing_decision_ids: list[str] = Field(default_factory=list)
    missing_check_ids: list[str] = Field(default_factory=list)


class ExperimentGateResult(ModelBase):
    kind: ExperimentGateKind
    reason: str | None = None
    missing_module_ids: list[str] = Field(default_factory=list)
    missing_decision_ids: list[str] = Field(default_factory=list)
    missing_check_ids: list[str] = Field(default_factory=list)


class AdoptionEvaluation(ModelBase):
    kind: AdoptionEvaluationKind
    reason: str | None = None
    adopted_item: object | None = None
