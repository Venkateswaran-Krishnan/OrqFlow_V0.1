from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.runtime.process_runtime import initialize_process_scheduler
from framework.runtime.queue_db import initialize_queue_db_adapter
from framework.state import OrqflowState

FRAMEWORK_INIT_STATE = "FRAMEWORK_INIT"


def initialize_framework(state: OrqflowState) -> OrqflowState:
    logger = get_logger("runtime.framework")
    try:
        state["key_steps"] = _read_key_steps(state)
        logger.info("KeySteps loaded")
        logger.debug(
            "KeySteps loaded: path=%s, shape=%s, columns=%s",
            _key_steps_path(state),
            state["key_steps"].shape,
            list(state["key_steps"].columns),
        )
        initialize_process_scheduler(state)
        state["queue_db"] = initialize_queue_db_adapter(state)
        logger.info("Queue database initialized")
        logger.debug("Queue database details: %s", state["queue_db"].describe())
        _run_framework_init_hook(state)
    except Exception as error:
        logger.exception("Framework initialization failed")
        runtime = state["runtime_config"]
        runtime["last_status"] = Outcome.SYSTEM_EXCEPTION
        runtime["last_error"] = str(error)
        runtime["next_action"] = "END"
        return state

    logger.info("Framework lifecycle initialized")
    return state


def _run_framework_init_hook(state: OrqflowState) -> None:
    module_spec = _select_framework_init_module(state)
    logger = get_logger("runtime.framework")
    if module_spec is None:
        logger.info("Project framework initialization hook skipped")
        return

    logger.info("Project framework initialization hook started")
    logger.debug("Project framework initialization module: %s", module_spec)
    initialize_project = _load_framework_init_function(module_spec)
    initialize_project(state)
    logger.info("Project framework initialization hook completed")


def _select_framework_init_module(state: OrqflowState) -> str | None:
    key_steps = state.get("key_steps")
    if not isinstance(key_steps, pd.DataFrame):
        raise TypeError("KeySteps data is not loaded")
    if "State" not in key_steps.columns:
        raise ValueError("KeySteps is missing required column(s): State")

    matching_rows = [
        row
        for _, row in key_steps.iterrows()
        if str(row["State"]).strip().upper() == FRAMEWORK_INIT_STATE
    ]
    if not matching_rows:
        return None
    if len(matching_rows) > 1:
        raise ValueError("KeySteps must contain at most one FRAMEWORK_INIT row")
    if "Module" not in key_steps.columns:
        raise ValueError("KeySteps is missing required column(s): Module")

    module_value = matching_rows[0]["Module"]
    if module_value is None or pd.isna(module_value) or not str(module_value).strip():
        return None
    return str(module_value).strip()


def _load_framework_init_function(
    module_spec: str,
) -> Callable[[OrqflowState], Any]:
    module_name, separator, function_name = module_spec.partition(":")
    module_name = module_name.strip()
    function_name = function_name.strip()
    if not separator or not module_name or not function_name:
        raise ValueError(
            "Framework initialization Module must use the format "
            "'package.module:function'"
        )

    module = importlib.import_module(module_name)
    initialize_project = getattr(module, function_name, None)
    if not callable(initialize_project):
        raise TypeError(
            f"Configured framework initialization function is not callable: {module_spec}"
        )
    return initialize_project


def _read_key_steps(state: OrqflowState) -> Any:
    excel_module = _load_excel_utility(state)
    return excel_module.read_excel_dataframe(_key_steps_path(state))


def _load_excel_utility(state: OrqflowState) -> Any:
    excel_path = Path(state["config_context"]["share_root"]) / "common" / "excel.py"
    spec = importlib.util.spec_from_file_location("shared_excel", excel_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Excel utility could not be loaded: {excel_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _key_steps_path(state: OrqflowState) -> Path:
    return Path(state["config_context"]["project_config_dir"]) / "KeySteps.xlsx"
