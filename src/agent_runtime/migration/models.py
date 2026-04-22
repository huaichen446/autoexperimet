"""Phase 5 migration protocol models and typed outcomes."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from agent_runtime.models.common import ModelBase
from agent_runtime.models.execution import ExecutionGuide
from agent_runtime.models.runtime import ActionRecord, Module, Phase
from agent_runtime.models.skeleton import ExperimentOverview


class MigrationStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    FAILED = "failed"


class MigrationDecision(StrEnum):
    AUTO_RESUMED = "auto_resumed"
    PAUSED = "paused"
    ESCALATED = "escalated"


class MigrationMappingType(StrEnum):
    UNCHANGED = "unchanged"
    SPLIT = "split"
    MERGED = "merged"
    REMOVED = "removed"
    REORDERED = "reordered"
    CREATED = "created"


class MigrationItemResult(StrEnum):
    INHERITED = "inherited"
    FROZEN = "frozen"
    OBSOLETE = "obsolete"
    PAUSED = "paused"
    ESCALATED = "escalated"


class StateInheritanceMode(StrEnum):
    COPY = "copy"
    RESET = "reset"
    PARTIAL = "partial"
    NONE = "none"


class MigrationOutcomeKind(StrEnum):
    AUTO_RESUMED = "auto_resumed"
    PAUSE_MIGRATION = "pause_migration"
    ESCALATE_MIGRATION = "escalate_migration"


class ModuleMigrationItem(ModelBase):
    old_module_id: str | None = None
    new_module_id: str | None = None
    mapping_type: MigrationMappingType
    migration_result: MigrationItemResult
    state_inheritance_mode: StateInheritanceMode
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ModuleMigrationItem":
        if self.mapping_type == MigrationMappingType.REMOVED and self.new_module_id is not None:
            raise ValueError("removed module mappings must not include new_module_id")
        if self.mapping_type == MigrationMappingType.CREATED and self.old_module_id is not None:
            raise ValueError("created module mappings must not include old_module_id")
        if self.mapping_type != MigrationMappingType.CREATED and self.old_module_id is None:
            raise ValueError("non-created module mappings must include old_module_id")
        if self.mapping_type != MigrationMappingType.REMOVED and self.new_module_id is None:
            raise ValueError("non-removed module mappings must include new_module_id")
        return self


class PhaseMigrationItem(ModelBase):
    old_phase_id: str | None = None
    new_phase_id: str | None = None
    old_module_id: str | None = None
    new_module_id: str | None = None
    mapping_type: MigrationMappingType
    migration_result: MigrationItemResult
    state_inheritance_mode: StateInheritanceMode
    terminality_preserved: bool
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "PhaseMigrationItem":
        if self.mapping_type == MigrationMappingType.REMOVED and self.new_phase_id is not None:
            raise ValueError("removed phase mappings must not include new_phase_id")
        if self.mapping_type == MigrationMappingType.CREATED and self.old_phase_id is not None:
            raise ValueError("created phase mappings must not include old_phase_id")
        if self.mapping_type != MigrationMappingType.CREATED and self.old_phase_id is None:
            raise ValueError("non-created phase mappings must include old_phase_id")
        if self.mapping_type != MigrationMappingType.REMOVED and self.new_phase_id is None:
            raise ValueError("non-removed phase mappings must include new_phase_id")
        return self


class OverviewMigration(ModelBase):
    migration_id: str
    experiment_id: str
    from_overview_version: int = Field(ge=1)
    to_overview_version: int = Field(ge=1)
    migration_status: MigrationStatus
    module_mapping: list[ModuleMigrationItem] = Field(default_factory=list)
    phase_mapping: list[PhaseMigrationItem] = Field(default_factory=list)
    migration_decision: MigrationDecision | None = None
    resume_module_id: str | None = None
    resume_phase_id: str | None = None
    pause_reason_code: str | None = None
    escalate_reason_code: str | None = None
    created_at: str
    completed_at: str | None = None

    @model_validator(mode="after")
    def validate_versions(self) -> "OverviewMigration":
        if not self.migration_id:
            raise ValueError("migration_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if self.from_overview_version >= self.to_overview_version:
            raise ValueError("to_overview_version must be greater than from_overview_version")
        if self.migration_decision == MigrationDecision.AUTO_RESUMED:
            if not self.resume_module_id or not self.resume_phase_id:
                raise ValueError("auto_resumed migrations must include a unique resume point")
        return self


class MigrationRunResult(ModelBase):
    kind: MigrationOutcomeKind
    migration: OverviewMigration
    old_overview: ExperimentOverview
    new_overview: ExperimentOverview
    old_modules: list[Module]
    new_modules: list[Module]
    old_phases: list[Phase]
    new_phases: list[Phase]
    old_guides: list[ExecutionGuide]
    new_guide: ExecutionGuide | None = None
    historical_action_records: list[ActionRecord] = Field(default_factory=list)
    reason: str | None = None
