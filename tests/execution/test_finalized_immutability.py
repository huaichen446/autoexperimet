from __future__ import annotations

import pytest

from agent_runtime.execution import (
    abandon_attempt,
    block_attempt,
    complete_attempt,
    create_attempt,
    fail_attempt,
    finalize_attempt,
    route_late_async_result,
    start_running,
)
from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionRecord,
    ActionRecordStatus,
    ActionType,
    BlockedReason,
    ExternalCorrelationKey,
    FailureReason,
    WaitingTarget,
)


def build_action() -> Action:
    return Action(
        action_id="action-1",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        overview_version=1,
        title="Finalize action",
        action_type=ActionType.EXTERNAL_TOOL,
        executor_type=ActionExecutorHint.TOOL,
        instruction="Wait for external tool.",
        expected_output="Tool output.",
        required_inputs=[],
        decision_item_refs=[],
        done_check_refs=[],
        expected_output_refs=[],
        retry_policy="fixed",
        max_retry=1,
        priority=1,
        declared_order=0,
    )


def finalized_record() -> ActionRecord:
    action = build_action()
    records: list[ActionRecord] = []
    record = create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T13:00:00Z")
    start_running(record, started_at="2026-04-21T13:01:00Z")
    complete_attempt(record, {"result": "ok"}, terminal_at="2026-04-21T13:02:00Z")
    record.external_correlation_key = ExternalCorrelationKey(
        correlation_type="external_tool_request",
        correlation_key="tool-123",
    )
    finalize_attempt(record, finalized_at="2026-04-21T13:03:00Z")
    return record


def test_finalized_records_reject_business_state_mutation() -> None:
    record = finalized_record()

    with pytest.raises(ValueError, match="finalized action records cannot be business-state mutated"):
        complete_attempt(record, {"result": "late-change"}, terminal_at="2026-04-21T13:04:00Z")


def test_late_async_result_routes_to_late_arrival_record_without_mutating_attempt() -> None:
    record = finalized_record()
    before_output = dict(record.output_snapshot or {})
    late_arrivals = []

    late = route_late_async_result(
        record,
        {"tool_result": "late"},
        late_arrivals,
        late_arrival_id="late-1",
        received_at="2026-04-21T13:05:00Z",
    )

    assert record.output_snapshot == before_output
    assert late.payload == {"tool_result": "late"}
    assert late.action_record_id == record.action_record_id
    assert len(late_arrivals) == 1


def test_finalize_attempt_rejects_non_terminal_states() -> None:
    action = build_action()

    selected_records: list[ActionRecord] = []
    selected = create_attempt(action, selected_records, action_record_id="selected-record", created_at="2026-04-21T14:00:00Z")
    with pytest.raises(ValueError, match="only done, failed, or abandoned attempts may be finalized"):
        finalize_attempt(selected, finalized_at="2026-04-21T14:00:30Z")

    running_records: list[ActionRecord] = []
    running = create_attempt(action, running_records, action_record_id="running-record", created_at="2026-04-21T14:01:00Z")
    start_running(running, started_at="2026-04-21T14:01:30Z")
    with pytest.raises(ValueError, match="only done, failed, or abandoned attempts may be finalized"):
        finalize_attempt(running, finalized_at="2026-04-21T14:02:00Z")

    blocked_records: list[ActionRecord] = []
    blocked = create_attempt(action, blocked_records, action_record_id="blocked-record", created_at="2026-04-21T14:03:00Z")
    start_running(blocked, started_at="2026-04-21T14:03:30Z")
    block_attempt(
        blocked,
        BlockedReason(
            blocked_reason_type="external_tool_not_ready",
            code="tool-wait",
            message="waiting",
            retryable_after_unblock=True,
        ),
        waiting_target=WaitingTarget(waiting_type="external_tool", target_id="tool-1", correlation_key="corr-1"),
    )
    with pytest.raises(ValueError, match="only done, failed, or abandoned attempts may be finalized"):
        finalize_attempt(blocked, finalized_at="2026-04-21T14:04:00Z")


def test_abandoned_attempt_may_be_finalized() -> None:
    action = build_action()
    records: list[ActionRecord] = []
    record = create_attempt(action, records, action_record_id="abandoned-record", created_at="2026-04-21T14:10:00Z")
    abandon_attempt(record, terminal_at="2026-04-21T14:10:30Z")

    finalized = finalize_attempt(record, finalized_at="2026-04-21T14:11:00Z")

    assert finalized.attempt_status == ActionRecordStatus.ABANDONED
    assert finalized.finalized is True
    assert finalized.finalized_at == "2026-04-21T14:11:00Z"
