from __future__ import annotations

from pydantic import ValidationError
import pytest

from agent_runtime.execution import (
    abandon_attempt,
    block_attempt,
    complete_attempt,
    create_attempt,
    ensure_single_active_attempt,
    fail_attempt,
    get_active_attempt_for_action,
    resume_attempt,
    start_running,
    validate_required_input_definitions,
    validate_required_inputs,
)
from agent_runtime.models import (
    Action,
    ActionExecutorHint,
    ActionRecord,
    ActionRecordStatus,
    ActionType,
    BlockedReason,
    FailureReason,
    RequiredInput,
    WaitingTarget,
)


def build_action(*, action_id: str = "action-1", action_type: ActionType = ActionType.AUTO) -> Action:
    executor_type = {
        ActionType.AUTO: ActionExecutorHint.AGENT,
        ActionType.EXTERNAL_TOOL: ActionExecutorHint.TOOL,
        ActionType.HUMAN_INPUT: ActionExecutorHint.HUMAN,
    }[action_type]
    return Action(
        action_id=action_id,
        experiment_id="exp-1",
        module_id="module-1",
        phase_id="phase-1",
        guide_id="guide-1",
        overview_version=1,
        title="Collect evidence",
        action_type=action_type,
        executor_type=executor_type,
        instruction="Do the thing.",
        expected_output="A structured result.",
        required_inputs=[],
        decision_item_refs=[],
        done_check_refs=[],
        expected_output_refs=[],
        retry_policy="fixed",
        max_retry=2,
        priority=1,
        declared_order=0,
    )


def build_blocked_reason(reason_type: str) -> BlockedReason:
    return BlockedReason(
        blocked_reason_type=reason_type,
        code=reason_type,
        message=f"{reason_type} waiting",
        retryable_after_unblock=True,
    )


def build_failure_reason(*, counts_as_retry: bool = True) -> FailureReason:
    return FailureReason(
        category="transient_failure" if counts_as_retry else "invalid_input",
        code="failure",
        message="Something went wrong.",
        retryable=counts_as_retry,
        counts_as_retry=counts_as_retry,
    )


def test_single_active_attempt_invariant_rejects_second_active_attempt() -> None:
    action = build_action()
    records: list[ActionRecord] = []
    create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T10:00:00Z")

    with pytest.raises(ValueError, match="multiple active attempts"):
        create_attempt(action, records, action_record_id="record-2", created_at="2026-04-21T10:01:00Z")


def test_single_active_attempt_validator_rejects_multiple_active_records() -> None:
    action = build_action()
    first_records: list[ActionRecord] = []
    second_records: list[ActionRecord] = []
    first = create_attempt(action, first_records, action_record_id="record-1", created_at="2026-04-21T10:00:00Z")
    second = create_attempt(
        build_action(action_id="action-2"),
        second_records,
        action_record_id="record-2",
        created_at="2026-04-21T10:01:00Z",
    )
    second.action_id = first.action_id

    with pytest.raises(ValueError, match="at most one active attempt"):
        ensure_single_active_attempt([first, second])


def test_terminal_field_requirements_are_enforced() -> None:
    with pytest.raises(ValidationError, match="blocked action records must include blocked_reason"):
        ActionRecord(
            action_record_id="record-1",
            experiment_id="exp-1",
            module_id="module-1",
            phase_id="phase-1",
            guide_id="guide-1",
            action_id="action-1",
            overview_version=1,
            attempt_index=1,
            parent_attempt_index=None,
            action_type=ActionType.AUTO,
            executor_type="agent",
            attempt_status=ActionRecordStatus.BLOCKED,
            finalized=False,
            record_integrity="valid",
            input_snapshot={},
            execution_payload=None,
            output_snapshot=None,
            result_summary=None,
            failure_reason=None,
            blocked_reason=None,
            waiting_target=None,
            tool_request=None,
            tool_response=None,
            tool_call_status=None,
            request_target=None,
            request_payload=None,
            returned_input=None,
            evidence_refs=[],
            phase_writeback_hint="blocked",
            counts_as_retry=False,
            selected_at="2026-04-21T10:00:00Z",
            started_at="2026-04-21T10:01:00Z",
            terminal_at=None,
            created_at="2026-04-21T10:00:00Z",
            finalized_at=None,
            external_correlation_key=None,
            record_revision=1,
            mutation_reason_code="invalid",
            mutation_log_required=False,
        )


def test_valid_and_invalid_attempt_transitions() -> None:
    action = build_action()
    records: list[ActionRecord] = []
    record = create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T10:00:00Z")

    start_running(record, started_at="2026-04-21T10:01:00Z")
    block_attempt(
        record,
        build_blocked_reason("external_resource_not_ready"),
        waiting_target=WaitingTarget(waiting_type="external_resource", target_id="ctx", correlation_key="ctx-1"),
    )
    resume_attempt(record, execution_payload={"step": "resume"})
    fail_attempt(record, build_failure_reason(), terminal_at="2026-04-21T10:02:00Z")

    assert record.attempt_status == ActionRecordStatus.FAILED

    with pytest.raises(ValueError, match="invalid action attempt transition"):
        complete_attempt(record, {"unexpected": True}, terminal_at="2026-04-21T10:03:00Z")


def test_selected_to_abandoned_is_a_real_attempt_but_not_retry() -> None:
    action = build_action()
    records: list[ActionRecord] = []
    record = create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T10:00:00Z")

    abandon_attempt(record, terminal_at="2026-04-21T10:01:00Z")

    assert record.attempt_status == ActionRecordStatus.ABANDONED
    assert record.counts_as_retry is False
    assert record.phase_writeback_hint == "notes_only"


def test_get_active_attempt_returns_current_active_record() -> None:
    action = build_action()
    records: list[ActionRecord] = []
    record = create_attempt(action, records, action_record_id="record-1", created_at="2026-04-21T10:00:00Z")

    active = get_active_attempt_for_action(records, action.action_id)

    assert active is record


def test_required_input_definition_duplicate_is_invalid_action() -> None:
    with pytest.raises(ValueError, match="invalid action"):
        validate_required_input_definitions(
            [
                RequiredInput(
                    input_key="topic",
                    source_type="guide",
                    required=True,
                    value_type="str",
                    materialization_stage="pre_select",
                ),
                RequiredInput(
                    input_key="topic",
                    source_type="guide",
                    required=True,
                    value_type="str",
                    materialization_stage="pre_select",
                ),
            ]
        )


def test_required_input_routing_for_missing_and_malformed_inputs() -> None:
    action = build_action()
    action.required_inputs = [
        RequiredInput(
            input_key="topic",
            source_type="guide",
            required=True,
            value_type="str",
            materialization_stage="pre_select",
        ),
        RequiredInput(
            input_key="payload",
            source_type="runtime_context",
            required=True,
            value_type="json",
            materialization_stage="pre_run",
        ),
    ]

    with pytest.raises(ValueError, match="blocked:guide_missing_info"):
        validate_required_inputs(action, {}, stage="pre_select")

    with pytest.raises(ValueError, match="failed:invalid_input"):
        validate_required_inputs(action, {"payload": "not-json"}, stage="pre_run")


def test_post_wait_required_input_routing_is_explicit() -> None:
    human_action = build_action(action_type=ActionType.HUMAN_INPUT)
    human_action.required_inputs = [
        RequiredInput(
            input_key="answer",
            source_type="human_input",
            required=True,
            value_type="str",
            materialization_stage="post_wait_resume",
        )
    ]
    with pytest.raises(ValueError, match="blocked:human_input_missing"):
        validate_required_inputs(human_action, {}, stage="post_wait_resume")

    tool_action = build_action(action_type=ActionType.EXTERNAL_TOOL)
    tool_action.required_inputs = [
        RequiredInput(
            input_key="tool_result",
            source_type="external_tool",
            required=True,
            value_type="json",
            materialization_stage="post_wait_resume",
        )
    ]
    with pytest.raises(ValueError, match="blocked:external_tool_not_ready"):
        validate_required_inputs(tool_action, {}, stage="post_wait_resume")

    resource_action = build_action()
    resource_action.required_inputs = [
        RequiredInput(
            input_key="resource_blob",
            source_type="external_resource",
            required=True,
            value_type="artifact_ref",
            materialization_stage="post_wait_resume",
        )
    ]
    with pytest.raises(ValueError, match="blocked:external_resource_not_ready"):
        validate_required_inputs(resource_action, {}, stage="post_wait_resume")
