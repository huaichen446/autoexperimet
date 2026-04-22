"""Execution protocol validators and record-truth helpers."""

from __future__ import annotations

from agent_runtime.models import ActionRecord, ActionRecordStatus


ACTIVE_ATTEMPT_STATES = {
    ActionRecordStatus.SELECTED,
    ActionRecordStatus.RUNNING,
    ActionRecordStatus.BLOCKED,
}


def validate_terminal_requirements(record: ActionRecord) -> ActionRecord:
    """Re-validate terminal requirements for a record."""

    return ActionRecord.model_validate(record.model_dump())


def validate_finalized_immutability(record: ActionRecord, updates: dict) -> None:
    """Reject business-state mutation after a record has been finalized."""

    if not record.finalized:
        return

    allowed_after_finalize = {"record_revision", "mutation_reason_code", "mutation_log_required"}
    attempted = {key for key, value in updates.items() if getattr(record, key) != value}
    disallowed = attempted - allowed_after_finalize
    if disallowed:
        raise ValueError("finalized action records cannot be business-state mutated")


def validate_migration_frozen_immutability(record: ActionRecord, updates: dict) -> None:
    """Reject business-state mutation after a record has been frozen for migration."""

    if record.frozen_by_migration_id is None:
        return

    allowed_after_freeze = {
        "record_revision",
        "mutation_reason_code",
        "mutation_log_required",
        "frozen_by_migration_id",
        "migrated_to_overview_version",
        "migrated_resume_module_id",
        "migrated_resume_phase_id",
    }
    attempted = {key for key, value in updates.items() if getattr(record, key) != value}
    disallowed = attempted - allowed_after_freeze
    if disallowed:
        raise ValueError("migration-frozen action records cannot be business-state mutated")


def latest_valid_record_for_action(records: list[ActionRecord], action_id: str) -> ActionRecord | None:
    """Return the latest valid record by attempt index for one action."""

    valid_records = [
        record
        for record in records
        if record.action_id == action_id and record.record_integrity in {"valid", "repaired"}
    ]
    if not valid_records:
        return None
    return max(valid_records, key=lambda record: (record.attempt_index, record.record_revision, record.created_at))


def compute_retry_count_from_records(records: list[ActionRecord], action_id: str) -> int:
    """Aggregate retry count from finalized valid action records only."""

    return sum(
        1
        for record in records
        if record.action_id == action_id
        and record.record_integrity in {"valid", "repaired"}
        and record.finalized
        and record.counts_as_retry
    )


def get_active_attempt_for_action(records: list[ActionRecord], action_id: str) -> ActionRecord | None:
    """Return the single active attempt for an action if present."""

    active_records = [
        record
        for record in records
        if record.action_id == action_id
        and record.record_integrity in {"valid", "repaired"}
        and record.attempt_status in ACTIVE_ATTEMPT_STATES
    ]
    if not active_records:
        return None
    ensure_single_active_attempt(active_records)
    return active_records[0]


def ensure_single_active_attempt(records: list[ActionRecord]) -> None:
    """Reject more than one active attempt for the same action."""

    active_records = [record for record in records if record.attempt_status in ACTIVE_ATTEMPT_STATES]
    action_ids = {record.action_id for record in active_records}
    for action_id in action_ids:
        count = sum(1 for record in active_records if record.action_id == action_id)
        if count > 1:
            raise ValueError("a single action may have at most one active attempt")
