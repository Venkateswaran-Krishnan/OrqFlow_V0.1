from __future__ import annotations

from framework.logging_config import get_logger
from framework.results import Outcome, StepResult
from framework.runtime_loader import load_runtime_module
from framework.state import OrqflowState


def store_result(state: OrqflowState, result: StepResult) -> None:
    runtime = state["runtime_config"]
    runtime["last_status"] = result.get("outcome", Outcome.SUCCESS)
    runtime["last_error"] = result.get("message")
    runtime["next_action"] = result.get("next_action")
    get_logger("services.runtime").debug("Stored step result: %s", result)


def clear_process_runtime(state: OrqflowState) -> None:
    state.pop("process_module", None)
    state.pop("process_module_app", None)


def ensure_process_module(state: OrqflowState) -> None:
    process_config = state["process_config"]
    active_app = process_config["app"]
    if state.get("process_module") is not None and state.get("process_module_app") == active_app:
        return

    state["process_module"] = load_runtime_module(
        process_config["process_module"],
        f"framework_runtime_process_{active_app}",
    )
    state["process_module_app"] = active_app
    get_logger("services.runtime").debug(
        "Process module loaded for app '%s': %s",
        active_app,
        process_config["process_module"],
    )


def next_after_success(state: OrqflowState) -> str:
    execution_config = state["execution_config"]
    runtime = state["runtime_config"]
    if execution_config.get("batch_enabled"):
        if runtime.get("batch_count", 0) >= execution_config.get("batch_limit", 0):
            return "END"
    return "GET_TRANSACTION"
