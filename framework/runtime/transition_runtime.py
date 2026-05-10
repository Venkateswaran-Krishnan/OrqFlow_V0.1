from __future__ import annotations

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.state import OrqflowState


def resolve_transition(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    outcome = Outcome(runtime["last_status"])
    txn = runtime.get("txn")
    requested_action = runtime.get("next_action")
    get_logger("runtime.transition").debug(
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
        if runtime.get("retry_count", 0) < _execution_config(state).get("retry_limit", 0):
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


def clear_process_runtime(state: OrqflowState) -> None:
    state.pop("process_module", None)
    state.pop("process_module_app", None)


def next_after_success(state: OrqflowState) -> str:
    execution_config = _execution_config(state)
    runtime = state["runtime_config"]
    if execution_config.get("batch_enabled"):
        if runtime.get("batch_count", 0) >= execution_config.get("batch_limit", 0):
            return "END"
    return "GET_TRANSACTION"


def _execution_config(state: OrqflowState) -> dict:
    return state.get("config", {}).get("execution_config", {})
