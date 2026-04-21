"""Minimal Phase 2 execution protocol helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from agent_runtime.models import (
    Action,
    ActionRecord,
    ActionRecordStatus,
    BlockedReason,
    FailureReason,
    RequiredInput,
    WaitingTarget,
)

from .validators import (
    ensure_single_active_attempt,
    validate_finalized_immutability,
    validate_terminal_requirements,
)


VALID_TRANSITIONS: dict[ActionRecordStatus, set[ActionRecordStatus]] = {
    ActionRecordStatus.SELECTED: {ActionRecordStatus.RUNNING, ActionRecordStatus.ABANDONED},
    ActionRecordStatus.RUNNING: {
        ActionRecordStatus.BLOCKED,
        ActionRecordStatus.FAILED,
        ActionRecordStatus.DONE,
    },
    ActionRecordStatus.BLOCKED: {ActionRecordStatus.RUNNING, ActionRecordStatus.ABANDONED},
    ActionRecordStatus.FAILED: set(),
    ActionRecordStatus.DONE: set(),
    ActionRecordStatus.ABANDONED: set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_required_input_definitions(required_inputs: list[RequiredInput]) -> None:
    """Validate action required-input declarations."""

    seen_keys: set[tuple[str, str]] = set()
    for required_input in required_inputs:
        key = (required_input.input_key, required_input.materialization_stage)
        if key in seen_keys:
            raise ValueError("invalid action: duplicate required_inputs definition")
        seen_keys.add(key)


def validate_required_inputs(
    action: Action,
    provided_inputs: dict,
    *,
    stage: str,
) -> None:
    """Route missing or malformed inputs according to Phase 2 protocol rules."""

    validate_required_input_definitions(action.required_inputs)
    stage_requirements = [item for item in action.required_inputs if item.materialization_stage == stage and item.required]

    for requirement in stage_requirements:
        if requirement.input_key not in provided_inputs or provided_inputs[requirement.input_key] is None:
            if stage in {"pre_select", "pre_run"} and requirement.source_type in {"guide", "runtime_context"}:
                raise ValueError("blocked:guide_missing_info")
            if stage == "post_wait_resume" and requirement.source_type == "human_input":
                raise ValueError("blocked:human_input_missing")
            if stage == "post_wait_resume" and requirement.source_type == "external_tool":
                raise ValueError("blocked:external_tool_not_ready")
            if stage == "post_wait_resume" and requirement.source_type == "external_resource":
                raise ValueError("blocked:external_resource_not_ready")
            raise ValueError("invalid action: missing structural required input")

        if not _value_matches_type(provided_inputs[requirement.input_key], requirement.value_type):
            raise ValueError("failed:invalid_input")


def create_attempt(
    action: Action,
    existing_records: list[ActionRecord],
    *,
    action_record_id: str,
    input_snapshot: dict | None = None,
    mutation_reason_code: str = "attempt_created",
    counts_as_retry: bool = False,
    parent_attempt_index: int | None = None,
    created_at: str | None = None,
) -> ActionRecord:
    """Create a new selected attempt after enforcing single-active-attempt rules."""

    validate_required_input_definitions(action.required_inputs)
    ensure_single_active_attempt(existing_records)
    if any(
        record.action_id == action.action_id
        and record.attempt_status in {
            ActionRecordStatus.SELECTED,
            ActionRecordStatus.RUNNING,
            ActionRecordStatus.BLOCKED,
        }
        for record in existing_records
    ):
        raise ValueError("a single action may not have multiple active attempts")

    next_attempt_index = 1 + max(
        (record.attempt_index for record in existing_records if record.action_id == action.action_id),
        default=0,
    )
    timestamp = created_at or utc_now()
    record = ActionRecord(
        action_record_id=action_record_id,
        experiment_id=action.experiment_id,
        module_id=action.module_id,
        phase_id=action.phase_id,
        guide_id=action.guide_id,
        action_id=action.action_id,
        overview_version=action.overview_version,
        attempt_index=next_attempt_index,
        parent_attempt_index=parent_attempt_index,
        action_type=action.action_type,
        executor_type=action.executor_type.value,
        attempt_status=ActionRecordStatus.SELECTED,
        finalized=False,
        record_integrity="valid",
        input_snapshot=input_snapshot or {},
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
        phase_writeback_hint="notes_only",
        counts_as_retry=counts_as_retry,
        selected_at=timestamp,
        started_at=None,
        terminal_at=None,
        created_at=timestamp,
        finalized_at=None,
        external_correlation_key=None,
        record_revision=1,
        mutation_reason_code=mutation_reason_code,
        mutation_log_required=False,
    )
    existing_records.append(record)
    return record


def start_running(
    record: ActionRecord,
    *,
    execution_payload: dict | None = None,
    started_at: str | None = None,
    mutation_reason_code: str = "attempt_started",
) -> ActionRecord:
    return _transition_record(
        record,
        to_status=ActionRecordStatus.RUNNING,
        mutation_reason_code=mutation_reason_code,
        execution_payload=execution_payload,
        started_at=started_at or utc_now(),
        phase_writeback_hint="in_progress",
    )


def block_attempt(
    record: ActionRecord,
    blocked_reason: BlockedReason,
    *,
    waiting_target: WaitingTarget | None = None,
    mutation_reason_code: str = "attempt_blocked",
) -> ActionRecord:
    if blocked_reason.blocked_reason_type in {
        "external_tool_not_ready",
        "human_input_missing",
        "external_resource_not_ready",
    } and waiting_target is None:
        raise ValueError("resumable blocked attempts require waiting_target")
    return _transition_record(
        record,
        to_status=ActionRecordStatus.BLOCKED,
        mutation_reason_code=mutation_reason_code,
        blocked_reason=blocked_reason,
        waiting_target=waiting_target,
        phase_writeback_hint="blocked",
    )


def resume_attempt(
    record: ActionRecord,
    *,
    returned_input: dict | None = None,
    tool_response: dict | None = None,
    execution_payload: dict | None = None,
    mutation_reason_code: str = "attempt_resumed",
) -> ActionRecord:
    if record.blocked_reason is None:
        raise ValueError("only blocked attempts can be resumed")
    if record.blocked_reason.blocked_reason_type not in {
        "external_tool_not_ready",
        "human_input_missing",
        "external_resource_not_ready",
    }:
        raise ValueError("blocked attempt is not resumable in-place")
    if record.waiting_target is None:
        raise ValueError("resumable blocked attempts require waiting_target")
    return _transition_record(
        record,
        to_status=ActionRecordStatus.RUNNING,
        mutation_reason_code=mutation_reason_code,
        returned_input=returned_input,
        tool_response=tool_response,
        execution_payload=execution_payload,
        blocked_reason=None,
        waiting_target=None,
        phase_writeback_hint="in_progress",
    )


def fail_attempt(
    record: ActionRecord,
    failure_reason: FailureReason,
    *,
    result_summary: dict | None = None,
    terminal_at: str | None = None,
    mutation_reason_code: str = "attempt_failed",
) -> ActionRecord:
    return _transition_record(
        record,
        to_status=ActionRecordStatus.FAILED,
        mutation_reason_code=mutation_reason_code,
        failure_reason=failure_reason,
        blocked_reason=None,
        waiting_target=None,
        result_summary=result_summary,
        counts_as_retry=failure_reason.counts_as_retry,
        terminal_at=terminal_at or utc_now(),
        phase_writeback_hint="failed",
    )


def complete_attempt(
    record: ActionRecord,
    output_snapshot: dict,
    *,
    result_summary: dict | None = None,
    terminal_at: str | None = None,
    mutation_reason_code: str = "attempt_completed",
) -> ActionRecord:
    return _transition_record(
        record,
        to_status=ActionRecordStatus.DONE,
        mutation_reason_code=mutation_reason_code,
        output_snapshot=output_snapshot,
        result_summary=result_summary,
        blocked_reason=None,
        waiting_target=None,
        terminal_at=terminal_at or utc_now(),
        phase_writeback_hint="done",
    )


def abandon_attempt(
    record: ActionRecord,
    *,
    terminal_at: str | None = None,
    mutation_reason_code: str = "attempt_abandoned",
) -> ActionRecord:
    return _transition_record(
        record,
        to_status=ActionRecordStatus.ABANDONED,
        mutation_reason_code=mutation_reason_code,
        blocked_reason=None,
        waiting_target=None,
        terminal_at=terminal_at or utc_now(),
        phase_writeback_hint="notes_only",
    )


def finalize_attempt(
    record: ActionRecord,
    *,
    finalized_at: str | None = None,
    mutation_reason_code: str = "attempt_finalized",
) -> ActionRecord:
    if record.attempt_status not in {
        ActionRecordStatus.DONE,
        ActionRecordStatus.FAILED,
        ActionRecordStatus.ABANDONED,
    }:
        raise ValueError("only done, failed, or abandoned attempts may be finalized")
    return _mutate_record(
        record,
        {
            "finalized": True,
            "finalized_at": finalized_at or utc_now(),
            "record_revision": record.record_revision + 1,
            "mutation_reason_code": mutation_reason_code,
        },
    )


def _transition_record(
    record: ActionRecord,
    *,
    to_status: ActionRecordStatus,
    mutation_reason_code: str,
    **updates,
) -> ActionRecord:
    validate_finalized_immutability(record, updates)
    if to_status not in VALID_TRANSITIONS.get(record.attempt_status, set()):
        raise ValueError("invalid action attempt transition")
    return _mutate_record(
        record,
        {
            "attempt_status": to_status,
            "record_revision": record.record_revision + 1,
            "mutation_reason_code": mutation_reason_code,
            **updates,
        },
    )


def _mutate_record(record: ActionRecord, updates: dict) -> ActionRecord:
    validate_finalized_immutability(record, updates)
    candidate = record.model_copy(update=updates)
    validated = validate_terminal_requirements(ActionRecord.model_validate(candidate.model_dump()))
    for field_name in ActionRecord.model_fields:
        setattr(record, field_name, getattr(validated, field_name))
    return record


def _value_matches_type(value: object, value_type: str) -> bool:
    if value_type == "str":
        return isinstance(value, str)
    if value_type == "json":
        return isinstance(value, (dict, list))
    if value_type == "table":
        return isinstance(value, list)
    if value_type == "artifact_ref":
        return isinstance(value, str)
    if value_type == "enum":
        return isinstance(value, str)
    if value_type == "bool":
        return isinstance(value, bool)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False
