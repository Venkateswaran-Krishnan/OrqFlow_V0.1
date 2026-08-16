from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.runtime.process_runtime import initialize_process_scheduler
from framework.runtime.queue_db import initialize_queue_db_adapter
from framework.state import OrqflowState


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
    except Exception as error:
        logger.exception("Framework initialization failed")
        runtime = state["runtime_config"]
        runtime["last_status"] = Outcome.SYSTEM_EXCEPTION
        runtime["last_error"] = str(error)
        runtime["next_action"] = "END"
        return state

    logger.info("Framework lifecycle initialized")
    return state


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
