"""Adoption/archive-layer document models."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import ModelBase


class AdoptedDesignItem(ModelBase):
    """Archived design item adopted from a prior phase/guide boundary."""

    item_id: str
    title: str
    content: str

    source_phase_id: str
    source_guide_id: str | None = None
    source_overview_version: int = Field(ge=1)

    acceptance_basis: str
    accepted_at: str

    @model_validator(mode="after")
    def validate_sources(self) -> "AdoptedDesignItem":
        if not self.item_id:
            raise ValueError("item_id must be present")
        if not self.source_phase_id:
            raise ValueError("source_phase_id must be present")
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

        item_ids = [item.item_id for item in self.adopted_design_items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("item_id values must be unique within an experiment main doc")
        return self
