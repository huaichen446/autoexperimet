from __future__ import annotations

import pytest

from agent_runtime.execution import block_attempt, create_attempt, resume_attempt, start_running
from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionRecord,
    ActionRecordStatus,
    ActionType,
    BlockedReason,
    RequiredInput,
    WaitingTarget,
)


def build_action(action_type: ActionType) -> Action:
    executor_type = {
        ActionType.AUTO: ActionExecutorHint.AGENT,
        ActionType.EXTERNAL_TOOL: ActionExecutorHint.TOOL,
        ActionType.HUMAN_INPUT: ActionExecutorHint.HUMAN,
    }[action_type]
    return Action(
        action_id=f"{action_type.value}-action",
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        overview_version=1,
        title="Wait for input",
        action_type=action_type,
        executor_type=executor_type,
        instruction="Wait and resume.",
        expected_output="Resumed execution.",
        required_inputs=[
            RequiredInput(
                input_key="resume_payload",
                source_type="human_input" if action_type == ActionType.HUMAN_INPUT else "external_tool",
                required=False,
                value_type="json",
                materialization_stage="post_wait_resume",
            )
        ],
        decision_item_refs=[],
        done_check_refs=[],
        expected_output_refs=[],
        retry_policy="none" if action_type == ActionType.HUMAN_INPUT else "fixed",
        max_retry=0,
        priority=1,
        declared_order=0,
    )


def build_blocked_reason(reason_type: str) -> BlockedReason:
    return BlockedReason(
        blocked_reason_type=reason_type,
        code=reason_type,
        message=f"waiting on {reason_type}",
        retryable_after_unblock=True,
    )


def make_blocked_attempt(action_type: ActionType, reason_type: str) -> ActionRecord:
    action = build_action(action_type)
    records: list[ActionRecord] = []
    record = create_attempt(action, records, action_record_id=f"{action_type.value}-record", created_at="2026-04-21T11:00:00Z")
    start_running(record, started_at="2026-04-21T11:01:00Z")
    block_attempt(
        record,
        build_blocked_reason(reason_type),
        waiting_target=WaitingTarget(
            waiting_type="human" if action_type == ActionType.HUMAN_INPUT else "external_tool",
            target_id="target-1",
            correlation_key="corr-1",
        ),
    )
    return record


def test_external_tool_waiting_resumes_same_attempt() -> None:
    record = make_blocked_attempt(ActionType.EXTERNAL_TOOL, "external_tool_not_ready")

    resumed = resume_attempt(record, tool_response={"ok": True})

    assert resumed.attempt_index == 1
    assert resumed.attempt_status == ActionRecordStatus.RUNNING
    assert resumed.tool_response == {"ok": True}


def test_human_input_waiting_resumes_same_attempt() -> None:
    record = make_blocked_attempt(ActionType.HUMAN_INPUT, "human_input_missing")

    resumed = resume_attempt(record, returned_input={"answer": "yes"})

    assert resumed.attempt_index == 1
    assert resumed.attempt_status == ActionRecordStatus.RUNNING
    assert resumed.returned_input == {"answer": "yes"}


def test_external_resource_waiting_resumes_same_attempt() -> None:
    record = make_blocked_attempt(ActionType.AUTO, "external_resource_not_ready")

    resumed = resume_attempt(record, execution_payload={"resource": "ready"})

    assert resumed.attempt_index == 1
    assert resumed.attempt_status == ActionRecordStatus.RUNNING
    assert resumed.execution_payload == {"resource": "ready"}


def test_repeated_human_request_creates_new_attempt_without_retry() -> None:
    action = build_action(ActionType.HUMAN_INPUT)
    records: list[ActionRecord] = []
    first = create_attempt(action, records, action_record_id="human-record-1", created_at="2026-04-21T11:00:00Z")
    start_running(first, started_at="2026-04-21T11:01:00Z")
    block_attempt(
        first,
        build_blocked_reason("human_input_missing"),
        waiting_target=WaitingTarget(waiting_type="human", target_id="human-1", correlation_key="human-corr-1"),
    )

    first.attempt_status = ActionRecordStatus.ABANDONED
    first.terminal_at = "2026-04-21T11:02:00Z"
    first.phase_writeback_hint = "notes_only"

    second = create_attempt(action, records, action_record_id="human-record-2", created_at="2026-04-21T11:03:00Z")

    assert second.attempt_index == 2
    assert second.counts_as_retry is False


def test_skipped_belongs_only_to_action_not_action_record() -> None:
    action = build_action(ActionType.AUTO)
    records: list[ActionRecord] = []
    action.status = "skipped"

    assert records == []


def test_resume_rejects_non_resumable_block_reason() -> None:
    record = make_blocked_attempt(ActionType.AUTO, "guide_missing_info")

    with pytest.raises(ValueError, match="not resumable"):
        resume_attempt(record, execution_payload={"ignored": True})


def test_resumable_blocked_record_without_waiting_target_is_rejected() -> None:
    action = build_action(ActionType.EXTERNAL_TOOL)
    records: list[ActionRecord] = []
    record = create_attempt(action, records, action_record_id="tool-record-x", created_at="2026-04-21T11:10:00Z")
    start_running(record, started_at="2026-04-21T11:10:30Z")

    with pytest.raises(ValueError, match="require waiting_target"):
        block_attempt(record, build_blocked_reason("external_tool_not_ready"))
