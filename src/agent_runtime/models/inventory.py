"""Aggregate inventory validator for cross-object relationships."""

from __future__ import annotations

from pydantic import Field, model_validator

from .adoption import ExperimentMainDoc
from .common import ModelBase
from .execution import ExecutionGuide
from .runtime import ActionRecord, Module, Phase
from .skeleton import ExperimentOverview


class ObjectInventory(ModelBase):
    """Graph-level inventory view used to validate binding and version boundaries."""

    experiment_overview: ExperimentOverview
    modules: list[Module] = Field(default_factory=list)
    phases: list[Phase] = Field(default_factory=list)
    guides: list[ExecutionGuide] = Field(default_factory=list)
    action_records: list[ActionRecord] = Field(default_factory=list)
    main_doc: ExperimentMainDoc | None = None

    @model_validator(mode="after")
    def validate_graph(self) -> "ObjectInventory":
        overview = self.experiment_overview
        module_overviews = {module.module_overview_id: module for module in overview.modules}
        phase_overviews = {
            phase.phase_overview_id: phase
            for module in overview.modules
            for phase in module.phase_overviews
        }

        modules_by_id: dict[str, Module] = {}
        for module in self.modules:
            if module.module_id in modules_by_id:
                raise ValueError("module_id values must be unique in the inventory")
            modules_by_id[module.module_id] = module

            if module.experiment_id != overview.experiment_id:
                raise ValueError("runtime modules must bind to the inventory experiment_id")
            if module.overview_version != overview.version:
                raise ValueError("module overview_version must match the experiment overview version")
            if module.module_overview_ref not in module_overviews:
                raise ValueError("module.module_overview_ref must reference a module overview in the skeleton")

        phases_by_id: dict[str, Phase] = {}
        phases_by_module_id: dict[str, list[Phase]] = {}
        for phase in self.phases:
            if phase.phase_id in phases_by_id:
                raise ValueError("phase_id values must be unique in the inventory")
            phases_by_id[phase.phase_id] = phase
            phases_by_module_id.setdefault(phase.module_id, []).append(phase)

            if phase.experiment_id != overview.experiment_id:
                raise ValueError("runtime phases must bind to the inventory experiment_id")
            if phase.overview_version != overview.version:
                raise ValueError("phase overview_version must match the experiment overview version")
            if phase.phase_overview_ref not in phase_overviews:
                raise ValueError("phase.phase_overview_ref must reference a phase overview in the skeleton")
            if phase.module_id not in modules_by_id:
                raise ValueError("phase.module_id must reference a runtime module in the inventory")

        for module in self.modules:
            module_phases = phases_by_module_id.get(module.module_id, [])
            if not module_phases:
                raise ValueError("each runtime module must own at least one runtime phase")

            module_phase_ids = {phase.phase_id for phase in module_phases}
            if set(module.phase_ids) != module_phase_ids:
                raise ValueError("module.phase_ids must match the phases bound to that module")

            module_overview = module_overviews[module.module_overview_ref]
            overview_phase_ids = {phase.phase_overview_id for phase in module_overview.phase_overviews}
            bound_phase_overviews = {phase.phase_overview_ref for phase in module_phases}
            if bound_phase_overviews != overview_phase_ids:
                raise ValueError("runtime phases must preserve bindings to the module overview phase set")

        guides_by_id: dict[str, ExecutionGuide] = {}
        action_to_guide: dict[str, str] = {}
        for guide in self.guides:
            if guide.guide_id in guides_by_id:
                raise ValueError("guide_id values must be unique in the inventory")
            guides_by_id[guide.guide_id] = guide

            if guide.experiment_id != overview.experiment_id:
                raise ValueError("execution guides must bind to the inventory experiment_id")
            if guide.overview_version != overview.version:
                raise ValueError("guide overview_version must match the experiment overview version")
            if guide.module_id not in modules_by_id:
                raise ValueError("execution guides must reference an existing runtime module")
            if guide.phase_id not in phases_by_id:
                raise ValueError("execution guides must reference an existing runtime phase")
            if phases_by_id[guide.phase_id].module_id != guide.module_id:
                raise ValueError("execution guides must bind phase_id and module_id consistently")

            for action in guide.actions:
                if action.action_id in action_to_guide:
                    raise ValueError("each action must belong to exactly one execution guide")
                action_to_guide[action.action_id] = guide.guide_id

        for record in self.action_records:
            if record.experiment_id != overview.experiment_id:
                raise ValueError("action records must bind to the inventory experiment_id")
            if record.overview_version != overview.version:
                raise ValueError("action record overview_version must match the experiment overview version")
            if record.module_id not in modules_by_id:
                raise ValueError("action records must reference an existing runtime module")
            if record.phase_id not in phases_by_id:
                raise ValueError("action records must reference an existing runtime phase")
            if phases_by_id[record.phase_id].module_id != record.module_id:
                raise ValueError("action records must bind phase_id and module_id consistently")
            if record.guide_id not in guides_by_id:
                raise ValueError("action records must reference an existing execution guide")
            if record.action_id not in action_to_guide:
                raise ValueError("action records must reference an action that exists in an execution guide")
            if action_to_guide[record.action_id] != record.guide_id:
                raise ValueError("action records must reference the execution guide that owns the action")

        if self.main_doc is not None:
            if self.main_doc.experiment_id != overview.experiment_id:
                raise ValueError("main_doc must bind to the inventory experiment_id")
            for item in self.main_doc.adopted_design_items:
                if item.source_phase_id not in phases_by_id:
                    raise ValueError("adopted design items must reference an existing runtime phase")
                if item.source_guide_id is not None and item.source_guide_id not in guides_by_id:
                    raise ValueError("adopted design items must reference an existing execution guide")
                if item.source_overview_version != overview.version:
                    raise ValueError("adopted design items must preserve the experiment overview version boundary")

        return self
