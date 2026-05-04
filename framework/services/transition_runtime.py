from __future__ import annotations

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.services.runtime_state import clear_process_runtime, next_after_success
from framework.state import OrqflowState


def resolve_transition(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    outcome = Outcome(runtime["last_status"])
    txn = runtime.get("txn")
    requested_action = runtime.get("next_action")
    get_logger("services.transition").debug(
        "Transition input. Outcome: %s, txn: %s, runtime: %s",
        outcome,
        txn,
        runtime,
    )

    if requested_action == "APP_SWITCH":
        clear_process_runtime(state)
        runtime["retry_count"] = 0
        runtime["txn"] = None
        runtime["next_action"] = "APP_SWITCH"
        return state

    if outcome == Outcome.SUCCESS:
        state["queue"].mark_success(txn)
        runtime["retry_count"] = 0
        runtime["txn"] = None
        runtime["next_action"] = next_after_success(state)
        return state

    if outcome == Outcome.BUSINESS_EXCEPTION:
        state["queue"].mark_skipped(txn, runtime.get("last_error"))
        runtime["retry_count"] = 0
        runtime["txn"] = None
        runtime["next_action"] = next_after_success(state)
        return state

    if outcome == Outcome.SYSTEM_EXCEPTION:
        if runtime.get("retry_count", 0) < state["execution_config"].get("retry_limit", 0):
            runtime["retry_count"] = runtime.get("retry_count", 0) + 1
            runtime["next_action"] = "RETRY"
            return state
        state["queue"].mark_failed(txn, runtime.get("last_error"))
        runtime["retry_count"] = 0
        runtime["txn"] = None
        runtime["next_action"] = next_after_success(state)
        return state

    runtime["next_action"] = "END"
    return state
