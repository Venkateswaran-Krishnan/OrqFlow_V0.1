from __future__ import annotations

from typing import Literal

from framework.logging_config import trace_event
from framework.results import Outcome
from framework.runtime.cleanup_runtime import cleanup_execution
from framework.runtime.application_runtime import login_application as login_application_runtime
from framework.runtime.execution_init_runtime import initialize_execution
from framework.runtime.framework_lifecycle import initialize_framework
from framework.runtime.process_runtime import execute_process_transaction
from framework.runtime.queue_runtime import (
    create_master_queue,
    get_next_transaction,
    is_master_queue_due,
    wait_for_master_queue_schedule,
)
from framework.runtime.transition_runtime import has_periodic_master_queue, resolve_transition
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


def master_queue_wait(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:MASTER_QUEUE_WAIT")
    return wait_for_master_queue_schedule(state)


def get_transaction(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:GET_TRANSACTION")
    return get_next_transaction(state)


def login_application(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:LOGIN_APPLICATION")
    return login_application_runtime(state)


def process_transaction(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:PROCESS_TRANSACTION")
    return execute_process_transaction(state)


def transition_hub(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    outcome = Outcome(runtime["last_status"])
    _log(state, f"NODE:TRANSITION_HUB:{outcome}")
    return resolve_transition(state)


def end(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:END")
    return cleanup_execution(state)


def route_after_framework_init(state: OrqflowState) -> Literal["execution_init", "end"]:
    if state["runtime_config"].get("next_action") == "END":
        return "end"
    return "execution_init"


def route_after_get(state: OrqflowState) -> Literal["login_application", "transition_hub"]:
    action = state["runtime_config"].get("next_action")
    if action == "PROCESS":
        return "login_application"
    return "transition_hub"


def route_after_execution_init(
    state: OrqflowState,
) -> Literal[
    "master_queue_creator",
    "master_queue_wait",
    "get_transaction",
    "login_application",
    "end",
]:
    runtime = state["runtime_config"]
    if runtime.get("next_action") == "END":
        return "end"
    if runtime.get("execution_init_reason") == "RETRY":
        return "login_application"
    if is_master_queue_due(state):
        return "master_queue_creator"

    if runtime.get("execution_init_reason") == "STARTUP":
        return "get_transaction"

    queue = state.get("queue")
    if queue is not None and queue.has_eligible_transactions():
        return "get_transaction"
    if has_periodic_master_queue(state):
        return "master_queue_wait"
    return "end"


def route_after_master_queue_creator(state: OrqflowState) -> Literal["get_transaction", "end"]:
    if state["runtime_config"].get("next_action") == "END":
        return "end"
    return "get_transaction"


def route_after_transition(state: OrqflowState) -> Literal["execution_init", "get_transaction", "end"]:
    action = state["runtime_config"].get("next_action")
    if action in {"APP_SWITCH", "BATCH_COMPLETE", "MASTER_QUEUE_REFRESH", "RETRY"}:
        return "execution_init"
    if action == "GET_TRANSACTION":
        return "get_transaction"
    if action == "END":
        return "end"
    return "get_transaction"


def _log(state: OrqflowState, event: str) -> None:
    trace_event(state, event)
