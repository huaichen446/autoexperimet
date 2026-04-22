"""Skeleton-layer overview models and version boundaries."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import AuditStatus, DecompositionFeasibility, ModelBase


class PhaseOverview(ModelBase):
    """Stable skeleton definition for a phase within one module overview version."""

    phase_overview_id: str
    module_overview_id: str
    experiment_id: str
    overview_version: int = Field(ge=1)

    name: str
    role: str
    state_after: str
    why_phase_not_action: str
    transition_to_next: str

    sort_index: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_bindings(self) -> "PhaseOverview":
        if not self.phase_overview_id:
            raise ValueError("phase_overview_id must be present")
        if not self.module_overview_id:
            raise ValueError("module_overview_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        return self


class ModuleOverview(ModelBase):
    """Stable skeleton definition for a module within one experiment overview version."""

    module_overview_id: str
    experiment_id: str
    overview_version: int = Field(ge=1)

    name: str
    goal: str
    why_independent: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    contribution_to_experiment: str

    phase_overviews: list[PhaseOverview] = Field(min_length=1)
    phase_convergence_note: str

    depends_on_module_names: list[str] = Field(default_factory=list)
    sort_index: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_phase_relationships(self) -> "ModuleOverview":
        if not self.module_overview_id:
            raise ValueError("module_overview_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")

        phase_ids = set()
        for phase in self.phase_overviews:
            if phase.phase_overview_id in phase_ids:
                raise ValueError("phase_overview_id values must be unique within a module overview")
            phase_ids.add(phase.phase_overview_id)

            if phase.module_overview_id != self.module_overview_id:
                raise ValueError("phase_overviews must bind to their parent module_overview_id")
            if phase.experiment_id != self.experiment_id:
                raise ValueError("phase_overviews must bind to the same experiment_id as the module overview")
            if phase.overview_version != self.overview_version:
                raise ValueError("phase_overviews must preserve the parent overview_version")
        return self


class ExperimentOverview(ModelBase):
    """Stable skeleton snapshot for the experiment decomposition boundary."""

    overview_id: str
    experiment_id: str
    version: int = Field(ge=1)
    parent_version: int | None = Field(default=None, ge=1)

    experiment_title: str
    experiment_description: str
    experiment_environment: str | None = None
    experiment_objective: str

    module_decomposition_feasibility: DecompositionFeasibility
    module_decomposition_rationale: list[str] = Field(default_factory=list)

    modules: list[ModuleOverview] = Field(min_length=1)

    experiment_convergence_note: str
    failure_localization_note: str

    audit_status: AuditStatus
    audit_issue_summary: list[str] = Field(default_factory=list)
    audit_passed_at: str | None = None

    change_summary: str | None = None
    structural_change_summary: list[str] = Field(default_factory=list)
    created_at: str
    superseded_by_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_module_relationships(self) -> "ExperimentOverview":
        if not self.overview_id:
            raise ValueError("overview_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if self.parent_version is not None and self.parent_version >= self.version:
            raise ValueError("parent_version must be lower than version")
        if self.audit_status == AuditStatus.PASSED and not self.audit_passed_at:
            raise ValueError("audit_passed_at is required when audit_status is passed")

        module_ids = set()
        for module in self.modules:
            if module.module_overview_id in module_ids:
                raise ValueError("module_overview_id values must be unique within an experiment overview")
            module_ids.add(module.module_overview_id)

            if module.experiment_id != self.experiment_id:
                raise ValueError("module overviews must bind to the same experiment_id as the experiment overview")
            if module.overview_version != self.version:
                raise ValueError("module overviews must preserve the experiment overview version boundary")
        return self
