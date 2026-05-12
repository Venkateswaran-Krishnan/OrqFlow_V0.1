from __future__ import annotations

from typing import Literal

from framework.logging_config import get_logger, trace_event
from framework.results import Outcome
from framework.runtime.cleanup_runtime import cleanup_execution
from framework.runtime.application_runtime import login_application as login_application_runtime
from framework.runtime.framework_lifecycle import initialize_framework
from framework.runtime.queue_runtime import create_master_queue, get_next_transaction
from framework.runtime.transition_runtime import resolve_transition
from framework.state import OrqflowState


def framework_init(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:FRAMEWORK_INIT")
    return initialize_framework(state)


def execution_init(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:EXECUTION_INIT")
    return state


def master_queue_creator(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:MASTER_QUEUE_CREATOR")
    return create_master_queue(state)


def get_transaction(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:GET_TRANSACTION")
    return get_next_transaction(state)


def login_application(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:LOGIN_APPLICATION")
    return login_application_runtime(state)


def process_transaction(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:PROCESS_TRANSACTION")
    runtime = state["runtime_config"]
    runtime["last_status"] = Outcome.SUCCESS
    runtime["last_error"] = None
    runtime["next_action"] = None
    if runtime.get("first_run"):
        runtime["first_run"] = False
        get_logger("nodes").info("First run completed; runtime first_run marked false")
    return state


def transition_hub(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    outcome = Outcome(runtime["last_status"])
    _log(state, f"NODE:TRANSITION_HUB:{outcome}")
    return resolve_transition(state)


def end(state: OrqflowState) -> OrqflowState:
    _log(state, "NODE:END")
    return cleanup_execution(state)


def route_after_get(state: OrqflowState) -> Literal["login_application", "transition_hub"]:
    action = state["runtime_config"].get("next_action")
    if action == "PROCESS":
        return "login_application"
    return "transition_hub"


def route_after_execution_init(state: OrqflowState) -> Literal["master_queue_creator", "get_transaction"]:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    if settings.get("masterbot") is True:
        return "master_queue_creator"
    return "get_transaction"


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
