from __future__ import annotations

from typing import Literal

from framework.logging_config import trace_event
from framework.results import Outcome
from framework.services.cleanup_runtime import cleanup_execution
from framework.services.execution_lifecycle import initialize_execution
from framework.services.framework_lifecycle import initialize_framework
from framework.services.queue_runtime import create_master_queue, get_next_transaction
from framework.services.transaction_runtime import process_current_transaction
from framework.services.transition_runtime import resolve_transition
from framework.state import OrqflowState


def framework_init(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:FRAMEWORK_INIT")
    return initialize_framework(state)


def execution_init(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:EXECUTION_INIT")
    return initialize_execution(state)


def master_queue_creator(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:MASTER_QUEUE_CREATOR")
    return create_master_queue(state)


def get_transaction(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:GET_TRANSACTION")
    return get_next_transaction(state)


def process_transaction(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:PROCESS_TRANSACTION")
    return process_current_transaction(state)


def transition_hub(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    outcome = Outcome(runtime["last_status"])
    _log(state, f"NODE:TRANSITION_HUB:{outcome}")
    return resolve_transition(state)


def end(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:END")
    return cleanup_execution(state)


def route_after_get(state: OrqflowState) -> Literal["process_transaction", "get_transaction", "end"]:
    action = state["runtime_config"].get("next_action")
    if action == "PROCESS":
        return "process_transaction"
    if action == "WAIT":
        return "get_transaction"
    if action == "END":
        return "end"
    return "end"


def route_after_transition(state: OrqflowState) -> Literal["execution_init", "get_transaction", "end"]:
    action = state["runtime_config"].get("next_action")
    if action in {"APP_SWITCH", "RETRY"}:
        return "execution_init"
    if action == "GET_TRANSACTION":
        return "get_transaction"
    if action == "END":
        return "end"
    return "get_transaction"


def _log(state: OrqflowState, event: str) -> None:
    trace_event(state, event)
