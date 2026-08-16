from __future__ import annotations

import importlib
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import pandas as pd

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.runtime.process_runtime import activate_next_process_step
from framework.state import OrqflowState


EXECUTION_INIT_STATE = "EXECUTION_INIT"
STARTUP_REASON = "STARTUP"
RESET_REASONS = {"BATCH_COMPLETE", "APP_SWITCH", "RETRY"}
VALID_REASONS = RESET_REASONS | {STARTUP_REASON, "MASTER_QUEUE_REFRESH"}


def initialize_execution(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.execution_init")

    try:
        reason = _execution_init_reason(runtime)
        current_application_id = runtime.get("active_application_id")
        logger.info("Execution initialization started")
        logger.debug(
            "Execution initialization details: reason=%s, application_id=%s, "
            "session_batch_count=%s",
            reason,
            current_application_id,
            runtime.get("session_batch_count"),
        )

        if reason in RESET_REASONS:
            _run_application_reset_hook(state, current_application_id)
            runtime["application_logged_in"] = False

            if reason in {"BATCH_COMPLETE", "APP_SWITCH"}:
                activate_next_process_step(state)
            else:
                runtime["session_batch_count"] = 0

            logger.info("Application session reset completed")
            logger.debug(
                "Application session reset details: reason=%s, previous_application_id=%s, "
                "active_application_id=%s, session_batch_count=%s",
                reason,
                current_application_id,
                runtime.get("active_application_id"),
                runtime.get("session_batch_count"),
            )
        elif reason == STARTUP_REASON:
            logger.info("Startup application session selected")
        else:
            logger.info("Execution initialization completed without an application reset")

        runtime["execution_init_reason"] = reason
        logger.info("Execution initialization completed")
    except Exception as error:
        logger.exception("Execution initialization failed")
        runtime["last_status"] = Outcome.SYSTEM_EXCEPTION
        runtime["last_error"] = str(error)
        runtime["next_action"] = "END"

    return state


def _execution_init_reason(runtime: dict[str, Any]) -> str:
    requested_action = str(runtime.get("next_action") or "").strip().upper()
    if requested_action in VALID_REASONS - {STARTUP_REASON}:
        reason = requested_action
    else:
        reason = str(runtime.get("execution_init_reason") or STARTUP_REASON).strip().upper()

    if reason not in VALID_REASONS:
        raise ValueError(f"Unsupported execution initialization reason: {reason!r}")
    return reason


def _run_application_reset_hook(
    state: OrqflowState,
    application_id: Any,
) -> None:
    if application_id is None:
        raise ValueError("runtime_config.active_application_id is required")

    module_spec = _select_execution_init_module(state, application_id)
    logger = get_logger("runtime.execution_init")
    if module_spec is None:
        logger.info("Application reset hook skipped; no matching KeySteps entry")
        logger.debug(
            "Application reset hook lookup: state=%s, application_id=%s",
            EXECUTION_INIT_STATE,
            application_id,
        )
        return

    logger.info("Application reset hook started")
    logger.debug(
        "Application reset hook details: application_id=%s, module=%s",
        application_id,
        module_spec,
    )
    reset_function = _load_execution_init_function(module_spec)
    reset_function(state)
    logger.info("Application reset hook completed")


def _select_execution_init_module(
    state: OrqflowState,
    application_id: Any,
) -> str | None:
    key_steps = state.get("key_steps")
    if not isinstance(key_steps, pd.DataFrame):
        raise ValueError("KeySteps data is not loaded")

    required_columns = {"State", "Application", "Module"}
    missing_columns = sorted(required_columns.difference(key_steps.columns))
    if missing_columns:
        raise ValueError(
            "KeySteps is missing required column(s): " + ", ".join(missing_columns)
        )

    matching_rows = []
    for workbook_order, (_, row) in enumerate(key_steps.iterrows()):
        if str(row["State"]).strip().upper() != EXECUTION_INIT_STATE:
            continue
        if not _application_matches(row["Application"], application_id):
            continue
        matching_rows.append((workbook_order, row))

    if not matching_rows:
        return None

    if "Sequence" in key_steps.columns:
        matching_rows.sort(
            key=lambda item: (_sequence_value(item[1]["Sequence"]), item[0])
        )
    module_value = matching_rows[0][1]["Module"]
    if module_value is None or pd.isna(module_value) or not str(module_value).strip():
        raise ValueError(
            f"KeySteps {EXECUTION_INIT_STATE} Module is required for Application "
            f"{application_id}"
        )
    return str(module_value).strip()


def _load_execution_init_function(
    module_spec: str,
) -> Callable[[OrqflowState], Any]:
    module_name, separator, function_name = module_spec.partition(":")
    module_name = module_name.strip()
    function_name = function_name.strip()
    if not separator or not module_name or not function_name:
        raise ValueError(
            "Execution initialization Module must use the format "
            "'package.module:function'"
        )

    module = importlib.import_module(module_name)
    reset_function = getattr(module, function_name, None)
    if not callable(reset_function):
        raise TypeError(
            f"Configured execution initialization function is not callable: {module_spec}"
        )
    return reset_function


def _application_matches(value: Any, expected: Any) -> bool:
    try:
        return Decimal(str(value).strip()) == Decimal(str(expected).strip())
    except (InvalidOperation, ValueError):
        return False


def _sequence_value(value: Any) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"KeySteps has invalid Sequence: {value!r}") from error
    if not number.is_finite():
        raise ValueError(f"KeySteps has invalid Sequence: {value!r}")
    return number
