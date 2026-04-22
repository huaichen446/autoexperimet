"""Action-layer resolution from the current valid execution guide."""

from __future__ import annotations

from agent_runtime.models import Action, ActionType, ExecutionGuide

from .helpers import (
    ESCALATION_REASONS,
    REVISE_REASONS,
    WAITING_REASONS,
    latest_truth,
    open_decision_ids,
    phase_repairable_locally,
    unmet_done_check_ids,
)
from .result_types import ActionResolution, ActionResolutionKind, SchedulerRuntimeState


def classify_blocked_action(action: Action, state: SchedulerRuntimeState) -> str | None:
    _, record, _ = latest_truth(action, state.inventory.action_records)
    blocked_reason = None
    if record is not None and record.blocked_reason is not None:
        blocked_reason = record.blocked_reason.blocked_reason_type
    elif action.last_blocked_reason is not None:
        blocked_reason = action.last_blocked_reason.blocked_reason_type
    if blocked_reason is not None and action.action_id in state.useful_returned_action_ids:
        if blocked_reason in {
            "external_tool_not_ready",
            "human_input_missing",
            "external_resource_not_ready",
        }:
            return None
    return blocked_reason


def resolve_current_action(state: SchedulerRuntimeState, guide: ExecutionGuide) -> ActionResolution:
    if guide.module_id != state.current_module_id or guide.phase_id != state.current_phase_id:
        return ActionResolution(kind=ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE, guide_id=guide.guide_id, reason="phase_guide_boundary_mismatch")
    guide_priority = _highest_priority_blocker(guide.blockers)
    if guide_priority is not None:
        return guide_priority.model_copy(update={"guide_id": guide.guide_id})

    current_action = _resolve_current_action_candidate(state, guide)
    if current_action is not None:
        blocked_reason = classify_blocked_action(current_action, state)
        if blocked_reason is not None:
            return _map_blocked_reason(blocked_reason, current_action.action_id, guide.guide_id)

        status, record, retry_count = latest_truth(current_action, state.inventory.action_records)
        if status.value in {"selected", "running"}:
            return ActionResolution(
                kind=ActionResolutionKind.CONTINUE_CURRENT_ACTION,
                action_id=current_action.action_id,
                guide_id=guide.guide_id,
            )
        if (
            status.value == "failed"
            and record is not None
            and record.failure_reason is not None
            and record.failure_reason.retryable
            and current_action.action_type != ActionType.HUMAN_INPUT
            and current_action.retry_policy != "none"
            and retry_count < current_action.max_retry
        ):
            return ActionResolution(
                kind=ActionResolutionKind.RETRY_CURRENT_ACTION,
                action_id=current_action.action_id,
                guide_id=guide.guide_id,
            )
        if status.value in {"failed", "abandoned", "done"}:
            alternative = _best_executable_action(state, guide, exclude_action_id=current_action.action_id)
            if alternative is not None:
                return ActionResolution(
                    kind=ActionResolutionKind.ABANDON_CURRENT_ACTION_AND_SWITCH,
                    action_id=alternative.action_id,
                    guide_id=guide.guide_id,
                    reason="switch_to_alternative_action",
                )

    selected = select_action_from_guide(guide, state)
    if selected is not None:
        return ActionResolution(
            kind=ActionResolutionKind.CONTINUE_CURRENT_ACTION,
            action_id=selected.action_id,
            guide_id=guide.guide_id,
        )
    return _resolve_no_executable_action(state, guide)


def select_action_from_guide(guide: ExecutionGuide, state: SchedulerRuntimeState) -> Action | None:
    return _best_executable_action(state, guide, exclude_action_id=None)


def _resolve_current_action_candidate(state: SchedulerRuntimeState, guide: ExecutionGuide) -> Action | None:
    if state.current_action_id is not None:
        return next((action for action in guide.actions if action.action_id == state.current_action_id), None)

    active_actions = []
    for action in guide.actions:
        status, _, _ = latest_truth(action, state.inventory.action_records)
        if status.value in {"selected", "running", "blocked"}:
            active_actions.append(action)
    if len(active_actions) == 1:
        return active_actions[0]
    return None


def _best_executable_action(state: SchedulerRuntimeState, guide: ExecutionGuide, exclude_action_id: str | None) -> Action | None:
    ranked = []
    open_decisions = open_decision_ids(guide)
    unmet_checks = unmet_done_check_ids(guide)

    for action in guide.actions:
        if exclude_action_id is not None and action.action_id == exclude_action_id:
            continue
        status, record, retry_count = latest_truth(action, state.inventory.action_records)
        blocked_reason = classify_blocked_action(action, state)
        if blocked_reason is not None:
            continue
        if status.value == "done":
            continue
        if status.value == "failed":
            if action.action_type == ActionType.HUMAN_INPUT:
                continue
            if (
                record is None
                or record.failure_reason is None
                or not record.failure_reason.retryable
                or action.retry_policy == "none"
                or retry_count >= action.max_retry
            ):
                continue
        decision_support = len(open_decisions.intersection(action.decision_item_refs))
        unmet_support = len(unmet_checks.intersection(action.done_check_refs))
        if decision_support == 0 and unmet_support == 0:
            continue
        selected_rank = 1 if status.value in {"selected", "running"} else 0
        ranked.append(
            (
                -decision_support,
                -unmet_support,
                -selected_rank,
                -action.priority,
                action.declared_order,
                action.action_id,
                action,
            )
        )
    if not ranked:
        return None
    return min(ranked)[-1]


def _highest_priority_blocker(blockers: list[str]) -> ActionResolution | None:
    for reason in blockers:
        if reason in ESCALATION_REASONS:
            return ActionResolution(kind=ActionResolutionKind.ESCALATE_TO_OVERVIEW_REVISION, reason=reason)
    for reason in blockers:
        if reason in REVISE_REASONS:
            return ActionResolution(kind=ActionResolutionKind.REVISE_GUIDE_KEEP_PHASE, reason=reason)
    for reason, result_kind in WAITING_REASONS.items():
        if reason in blockers:
            return ActionResolution(kind=ActionResolutionKind(result_kind), reason=reason)
    return None


def _map_blocked_reason(reason: str, action_id: str | None, guide_id: str) -> ActionResolution:
    if reason in ESCALATION_REASONS:
        return ActionResolution(
            kind=ActionResolutionKind.ESCALATE_TO_OVERVIEW_REVISION,
            action_id=action_id,
            guide_id=guide_id,
            reason=reason,
        )
    if reason == "guide_missing_info":
        return ActionResolution(
            kind=ActionResolutionKind.REVISE_GUIDE_KEEP_PHASE,
            action_id=action_id,
            guide_id=guide_id,
            reason=reason,
        )
    return ActionResolution(
        kind=ActionResolutionKind(WAITING_REASONS[reason]),
        action_id=action_id,
        guide_id=guide_id,
        reason=reason,
    )


def _resolve_no_executable_action(state: SchedulerRuntimeState, guide: ExecutionGuide) -> ActionResolution:
    waiting_actions = []
    has_any_supporting_action = False
    open_decisions = open_decision_ids(guide)
    unmet_checks = unmet_done_check_ids(guide)

    for action in guide.actions:
        decision_support = len(open_decisions.intersection(action.decision_item_refs))
        unmet_support = len(unmet_checks.intersection(action.done_check_refs))
        if decision_support > 0 or unmet_support > 0:
            has_any_supporting_action = True
        reason = classify_blocked_action(action, state)
        if reason in WAITING_REASONS:
            waiting_actions.append(action)

    if waiting_actions:
        selected = min(waiting_actions, key=lambda action: (-action.priority, action.declared_order, action.action_id))
        waiting_reason = classify_blocked_action(selected, state)
        return ActionResolution(
            kind=ActionResolutionKind.NO_EXECUTABLE_ACTION_PAUSE,
            action_id=selected.action_id,
            guide_id=guide.guide_id,
            reason=waiting_reason,
        )
    if not has_any_supporting_action:
        return ActionResolution(
            kind=ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE,
            guide_id=guide.guide_id,
            reason="no_action_supports_open_work",
        )
    if phase_repairable_locally(state, guide.phase_id):
        return ActionResolution(
            kind=ActionResolutionKind.NO_EXECUTABLE_ACTION_REVISE_GUIDE,
            guide_id=guide.guide_id,
            reason="repairable_within_phase",
        )
    return ActionResolution(
        kind=ActionResolutionKind.NO_EXECUTABLE_ACTION_ESCALATE,
        guide_id=guide.guide_id,
        reason="no_legal_action",
    )
