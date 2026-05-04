from __future__ import annotations

from framework.adapters import BrowserDriver, ObjectRepository
from framework.logging_config import get_logger
from framework.runtime_loader import load_runtime_module
from framework.services.runtime_state import clear_process_runtime, store_result
from framework.state import OrqflowState
from framework.steps import load_automation_steps, run_phase_steps


def initialize_execution(state: OrqflowState) -> OrqflowState:
    process_config = state["process_config"]
    get_logger("services.execution").debug("Process config: %s", process_config)

    state["init_module"] = load_runtime_module(process_config["init_module"], "framework_runtime_init")
    clear_process_runtime(state)
    state["automation_steps"] = load_automation_steps(process_config["automation_steps"])
    state["repo"] = ObjectRepository(process_config["object_repo_path"], process_config["app"])

    driver = state.get("driver")
    if driver is None:
        driver = BrowserDriver()
        driver.start()
        state["driver"] = driver
    else:
        driver.restart()

    result = run_phase_steps(state, "init")
    store_result(state, result)
    return state
