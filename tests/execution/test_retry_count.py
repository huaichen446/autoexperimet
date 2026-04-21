from __future__ import annotations

from agent_runtime.execution import (
    compute_retry_count_from_records,
    create_attempt,
    fail_attempt,
    finalize_attempt,
    latest_valid_record_for_action,
    repair_action_mirror_if_needed,
    start_running,
)
from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionRecord,
    ActionRecordStatus,
    ActionStatus,
    ActionType,
    FailureReason,
)


def build_action() -> Action:
    return Action(
        action_id="action-1",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        overview_version=1,
        title="Retry action",
        action_type=ActionType.AUTO,
        executor_type=ActionExecutorHint.AGENT,
        instruction="Try the work.",
        expected_output="Successful result.",
        required_inputs=[],
        decision_item_refs=[],
        done_check_refs=[],
        expected_output_refs=[],
        retry_policy="fixed",
        max_retry=3,
        priority=1,
        declared_order=0,
        status=ActionStatus.DONE,
        current_attempt_index=999,
        retry_count=999,
        last_failure_reason=None,
        last_blocked_reason=None,
        last_record_id="wrong-record",
    )


def build_failure(counts_as_retry: bool) -> FailureReason:
    return FailureReason(
        category="transient_failure" if counts_as_retry else "invalid_input",
        code="failure",
        message="failure",
        retryable=counts_as_retry,
        counts_as_retry=counts_as_retry,
    )


def test_retry_count_is_derived_from_valid_record_aggregation() -> None:
    action = build_action()
    records: list[ActionRecord] = []

    first = create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T12:00:00Z")
    start_running(first, started_at="2026-04-21T12:00:30Z")
    fail_attempt(first, build_failure(True), terminal_at="2026-04-21T12:01:00Z")
    finalize_attempt(first, finalized_at="2026-04-21T12:01:30Z")

    second = create_attempt(action, records, action_record_id="record-2", created_at="2026-04-21T12:02:00Z")
    start_running(second, started_at="2026-04-21T12:02:30Z")
    fail_attempt(second, build_failure(False), terminal_at="2026-04-21T12:03:00Z")
    finalize_attempt(second, finalized_at="2026-04-21T12:03:30Z")

    third = create_attempt(action, records, action_record_id="record-3", created_at="2026-04-21T12:04:00Z")
    third.attempt_status = ActionRecordStatus.ABANDONED
    third.terminal_at = "2026-04-21T12:05:00Z"
    third.phase_writeback_hint = "notes_only"
    third.record_integrity = "valid"

    assert compute_retry_count_from_records(records, action.action_id) == 1


def test_latest_valid_record_is_execution_truth_and_mirror_is_repaired() -> None:
    action = build_action()
    records: list[ActionRecord] = []

    invalid = create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T12:00:00Z")
    start_running(invalid, started_at="2026-04-21T12:00:30Z")
    fail_attempt(invalid, build_failure(True), terminal_at="2026-04-21T12:01:00Z")
    invalid.record_integrity = "invalid"

    truth = create_attempt(action, records, action_record_id="record-2", created_at="2026-04-21T12:02:00Z")
    start_running(truth, started_at="2026-04-21T12:02:30Z")
    fail_attempt(truth, build_failure(True), terminal_at="2026-04-21T12:03:00Z")
    finalize_attempt(truth, finalized_at="2026-04-21T12:03:30Z")

    latest = latest_valid_record_for_action(records, action.action_id)
    repaired = repair_action_mirror_if_needed(action, records)

    assert latest is truth
    assert repaired.status == ActionStatus.FAILED
    assert repaired.current_attempt_index == 2
    assert repaired.retry_count == 1
    assert repaired.last_record_id == "record-2"


def test_retry_count_ignores_non_finalized_failed_records() -> None:
    action = build_action()
    records: list[ActionRecord] = []

    first = create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T12:10:00Z")
    start_running(first, started_at="2026-04-21T12:10:30Z")
    fail_attempt(first, build_failure(True), terminal_at="2026-04-21T12:11:00Z")

    second = create_attempt(action, records, action_record_id="record-2", created_at="2026-04-21T12:12:00Z")
    start_running(second, started_at="2026-04-21T12:12:30Z")
    fail_attempt(second, build_failure(True), terminal_at="2026-04-21T12:13:00Z")
    finalize_attempt(second, finalized_at="2026-04-21T12:13:30Z")

    assert compute_retry_count_from_records(records, action.action_id) == 1
