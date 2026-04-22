"""Adoption/archive-layer document models."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import AdoptionStatus, ModelBase


class AdoptedDesignItem(ModelBase):
    """A promotion-ready or adopted design result bound to acceptance truth."""

    adopted_item_id: str
    experiment_id: str
    module_id: str | None = None
    phase_id: str | None = None
    guide_id: str | None = None
    overview_version: int = Field(ge=1)

    source_decision_id: str | None = None
    source_done_check_ids: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)

    adoption_scope: str
    adoption_type: str
    title: str
    content_snapshot: dict | list | str

    evidence_refs: list[str] = Field(default_factory=list)
    acceptance_basis: list[str] = Field(default_factory=list)
    adoption_status: AdoptionStatus
    adopted_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "adopted_item_id" not in data and "item_id" in data:
            data["adopted_item_id"] = data.pop("item_id")
        if "overview_version" not in data and "source_overview_version" in data:
            data["overview_version"] = data.pop("source_overview_version")
        if "phase_id" not in data and "source_phase_id" in data:
            data["phase_id"] = data.pop("source_phase_id")
        if "guide_id" not in data and "source_guide_id" in data:
            data["guide_id"] = data.pop("source_guide_id")
        if "content_snapshot" not in data and "content" in data:
            data["content_snapshot"] = data.pop("content")
        if "acceptance_basis" in data and isinstance(data["acceptance_basis"], str):
            data["acceptance_basis"] = [data["acceptance_basis"]]
        return data

    @model_validator(mode="after")
    def validate_sources(self) -> "AdoptedDesignItem":
        if not self.adopted_item_id:
            raise ValueError("adopted_item_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")
        if not self.title:
            raise ValueError("title must be present")
        if self.adoption_scope not in {"phase", "module", "experiment"}:
            raise ValueError("adoption_scope is not supported")
        if not self.adoption_type:
            raise ValueError("adoption_type must be present")
        if self.adoption_scope == "phase":
            if not self.module_id or not self.phase_id:
                raise ValueError("phase-scoped adopted items must bind module_id and phase_id")
        elif self.adoption_scope == "module":
            if not self.module_id:
                raise ValueError("module-scoped adopted items must bind module_id")
            if self.phase_id is not None:
                raise ValueError("module-scoped adopted items must not bind phase_id")
        elif self.module_id is not None or self.phase_id is not None:
            raise ValueError("experiment-scoped adopted items must not bind module_id or phase_id")
        if self.adoption_status in {AdoptionStatus.ADOPTED, AdoptionStatus.SUPERSEDED} and not self.adopted_at:
            raise ValueError("adopted and superseded items must include adopted_at")
        return self


class ExperimentMainDoc(ModelBase):
    """Top-level archive document for adopted design items."""

    doc_id: str
    experiment_id: str

    adopted_design_items: list[AdoptedDesignItem] = Field(default_factory=list)

    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def validate_items(self) -> "ExperimentMainDoc":
        if not self.doc_id:
            raise ValueError("doc_id must be present")
        if not self.experiment_id:
            raise ValueError("experiment_id must be present")

        item_ids = [item.adopted_item_id for item in self.adopted_design_items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("adopted_item_id values must be unique within an experiment main doc")
        return self
