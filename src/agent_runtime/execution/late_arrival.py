"""Late-arrival routing for finalized action attempts."""

from __future__ import annotations

from pydantic import Field, model_validator

from agent_runtime.models import ActionRecord, ExternalCorrelationKey
from agent_runtime.models.common import ModelBase


class LateArrivalRecord(ModelBase):
    """Captures async results that arrive after an attempt was finalized."""

    late_arrival_id: str
    action_record_id: str
    action_id: str
    attempt_index: int = Field(ge=1)
    correlation_key: ExternalCorrelationKey | None = None
    payload: dict
    received_at: str
    reason: str

    @model_validator(mode="after")
    def validate_shape(self) -> "LateArrivalRecord":
        if not self.late_arrival_id:
            raise ValueError("late_arrival_id must be present")
        if not self.action_record_id:
            raise ValueError("action_record_id must be present")
        if not self.action_id:
            raise ValueError("action_id must be present")
        if not self.reason:
            raise ValueError("reason must be present")
        return self


def route_late_async_result(
    record: ActionRecord,
    payload: dict,
    late_arrivals: list[LateArrivalRecord],
    *,
    late_arrival_id: str,
    received_at: str,
    reason: str = "finalized_record_late_arrival",
) -> LateArrivalRecord:
    """Route a late async result to a LateArrivalRecord instead of mutating the attempt."""

    if not record.finalized:
        raise ValueError("late async routing only applies to finalized records")

    late_arrival = LateArrivalRecord(
        late_arrival_id=late_arrival_id,
        action_record_id=record.action_record_id,
        action_id=record.action_id,
        attempt_index=record.attempt_index,
        correlation_key=record.external_correlation_key,
        payload=payload,
        received_at=received_at,
        reason=reason,
    )
    late_arrivals.append(late_arrival)
    return late_arrival
