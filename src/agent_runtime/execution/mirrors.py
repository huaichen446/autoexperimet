"""Helpers for syncing mirror-only action fields from record truth."""

from __future__ import annotations

from agent_runtime.models import Action, ActionRecord, ActionStatus

from .validators import compute_retry_count_from_records, latest_valid_record_for_action


def sync_action_mirror_from_record(action: Action, record: ActionRecord | None, records: list[ActionRecord]) -> Action:
    """Copy execution truth into mirror-only action cache fields."""

    if record is None:
        action.status = ActionStatus.PENDING
        action.current_attempt_index = None
        action.retry_count = compute_retry_count_from_records(records, action.action_id)
        action.last_failure_reason = None
        action.last_blocked_reason = None
        action.last_record_id = None
        return action

    action.status = ActionStatus(record.attempt_status.value)
    action.current_attempt_index = record.attempt_index
    action.retry_count = compute_retry_count_from_records(records, action.action_id)
    action.last_failure_reason = record.failure_reason
    action.last_blocked_reason = record.blocked_reason
    action.last_record_id = record.action_record_id
    return action


def repair_action_mirror_if_needed(action: Action, records: list[ActionRecord]) -> Action:
    """Repair divergent mirror fields using ActionRecord truth."""

    record = latest_valid_record_for_action(records, action.action_id)
    expected_retry_count = compute_retry_count_from_records(records, action.action_id)

    if record is None:
        if action.status != ActionStatus.PENDING or action.retry_count != expected_retry_count:
            sync_action_mirror_from_record(action, None, records)
        return action

    expected_status = ActionStatus(record.attempt_status.value)
    if (
        action.status != expected_status
        or action.current_attempt_index != record.attempt_index
        or action.retry_count != expected_retry_count
        or action.last_record_id != record.action_record_id
    ):
        sync_action_mirror_from_record(action, record, records)
    return action
