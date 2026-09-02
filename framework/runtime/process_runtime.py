from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import pandas as pd

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.state import OrqflowState


PROCESS_STATE = "PROCESS_TRANSACTION"
PROCESS_OUTCOMES = {
    Outcome.SUCCESS,
    Outcome.BUSINESS_EXCEPTION,
    Outcome.SYSTEM_EXCEPTION,
}


def initialize_process_scheduler(state: OrqflowState) -> OrqflowState:
    process_steps = load_process_steps(state)
    state["process_steps"] = process_steps
    _activate_process_step(state, 0)

    logger = get_logger("runtime.process")
    runtime = state["runtime_config"]
    logger.info("Process scheduler initialized")
    logger.debug(
        "Process scheduler state: step_count=%s, active_step_index=%s, "
        "active_application_id=%s, active_batch_limit=%s, session_batch_count=%s",
        len(process_steps),
        runtime["active_process_step_index"],
        runtime["active_application_id"],
        runtime["active_batch_limit"],
        runtime["session_batch_count"],
    )
    return state


def record_finalized_transaction(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    current_count = _nonnegative_integer(
        runtime.get("session_batch_count", 0),
        "runtime_config.session_batch_count",
    )
    runtime["session_batch_count"] = current_count + 1

    logger = get_logger("runtime.process")
    logger.info("Application session batch progress recorded")
    logger.debug(
        "Application session batch progress: application_id=%s, count=%s, limit=%s",
        runtime.get("active_application_id"),
        runtime["session_batch_count"],
        runtime.get("active_batch_limit"),
    )
    return state


def is_session_batch_complete(state: OrqflowState) -> bool:
    runtime = state["runtime_config"]
    batch_limit = runtime.get("active_batch_limit")
    if batch_limit is None:
        return False

    limit = _nonnegative_integer(
        batch_limit,
        "runtime_config.active_batch_limit",
    )
    if limit == 0:
        raise ValueError("runtime_config.active_batch_limit must be positive or None")
    count = _nonnegative_integer(
        runtime.get("session_batch_count", 0),
        "runtime_config.session_batch_count",
    )
    return count >= limit


def activate_next_process_step(state: OrqflowState) -> OrqflowState:
    process_steps = state.get("process_steps")
    if not isinstance(process_steps, list) or not process_steps:
        raise ValueError("state['process_steps'] is required for scheduler advancement")

    runtime = state["runtime_config"]
    current_index = _nonnegative_integer(
        runtime.get("active_process_step_index"),
        "runtime_config.active_process_step_index",
    )
    if current_index >= len(process_steps):
        raise ValueError("runtime_config.active_process_step_index is out of range")

    next_index = (current_index + 1) % len(process_steps)
    _activate_process_step(state, next_index)

    logger = get_logger("runtime.process")
    logger.info("Next process step activated")
    logger.debug(
        "Active process step: step_index=%s, application_id=%s, batch_limit=%s, "
        "session_batch_count=%s",
        runtime["active_process_step_index"],
        runtime["active_application_id"],
        runtime["active_batch_limit"],
        runtime["session_batch_count"],
    )
    return state


def _activate_process_step(state: OrqflowState, step_index: int) -> None:
    process_steps = state["process_steps"]
    active_step = process_steps[step_index]
    runtime = state["runtime_config"]
    runtime["active_process_step_index"] = step_index
    runtime["active_application_id"] = active_step["application_id"]
    runtime["active_batch_limit"] = active_step["batch_limit"]
    runtime["session_batch_count"] = 0


def execute_process_transaction(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.process")

    try:
        transaction = runtime.get("txn")
        if not isinstance(transaction, Mapping):
            raise ValueError("No active queue transaction is available")

        application_id = transaction.get("queue_application_details")
        if application_id is None or not str(application_id).strip():
            raise ValueError("Queue transaction has no application ID")

        selected_step = _select_process_step(state, application_id)
        module_spec = selected_step["module"]
        sequence = selected_step["sequence"]

        logger.info("Process transaction started")
        logger.debug(
            "Process transaction started: application_id=%s, sequence=%s, module=%s",
            application_id,
            sequence,
            module_spec,
        )

        process_function = _load_process_function(module_spec)
        result = process_function(state)
        outcome, message, data, next_action = _validate_result(result, module_spec)

        runtime["last_status"] = outcome
        runtime["last_error"] = None if outcome == Outcome.SUCCESS else message
        runtime["last_message"] = message
        runtime["last_result"] = data
        runtime["cto_details"] = _cto_details_from_result(data)
        runtime["next_action"] = next_action

        if outcome == Outcome.BUSINESS_EXCEPTION:
            logger.warning("Process transaction returned a business exception")
            logger.debug("Business exception message: %s", message)
        elif outcome == Outcome.SYSTEM_EXCEPTION:
            logger.error("Process transaction returned a system exception")
            logger.debug("System exception message: %s", message)

        if runtime.get("first_run"):
            runtime["first_run"] = False
            logger.info("First run completed; runtime first_run marked false")

        logger.info("Process transaction completed")
        logger.debug(
            "Process transaction completed: application_id=%s, sequence=%s, "
            "module=%s, outcome=%s",
            application_id,
            sequence,
            module_spec,
            outcome,
        )
    except Exception as error:
        logger.exception("Process transaction execution failed")
        runtime["last_status"] = Outcome.SYSTEM_EXCEPTION
        runtime["last_error"] = str(error)
        runtime["last_message"] = None
        runtime["last_result"] = {}
        runtime["cto_details"] = None
        runtime["next_action"] = None

    return state


def _select_process_step(state: OrqflowState, application_id: Any) -> Mapping[str, Any]:
    process_steps = state.get("process_steps")
    if not isinstance(process_steps, list) or not process_steps:
        process_steps = load_process_steps(state)
    matching_steps = [
        step
        for step in process_steps
        if _application_matches(step["application_id"], application_id)
    ]
    if not matching_steps:
        raise ValueError(
            f"No {PROCESS_STATE} step found for Application {application_id}"
        )
    return matching_steps[0]


def load_process_steps(state: OrqflowState) -> list[dict[str, Any]]:
    key_steps = state.get("key_steps")
    if not isinstance(key_steps, pd.DataFrame):
        raise ValueError("KeySteps data is not loaded")

    required_columns = {"Sequence", "State", "BatchCount", "Application", "Module"}
    missing_columns = sorted(required_columns.difference(key_steps.columns))
    if missing_columns:
        raise ValueError(
            "KeySteps is missing required column(s): " + ", ".join(missing_columns)
        )

    states = key_steps["State"].astype(str).str.strip().str.upper()
    process_steps = key_steps.loc[states == PROCESS_STATE].copy()
    if process_steps.empty:
        raise ValueError(f"KeySteps has no {PROCESS_STATE} rows")

    process_steps["_workbook_order"] = range(len(process_steps))
    process_steps["_excel_row"] = [
        position + 2
        for position, is_process_step in enumerate(states == PROCESS_STATE)
        if is_process_step
    ]
    process_steps["_numeric_sequence"] = pd.to_numeric(
        process_steps["Sequence"], errors="raise"
    )
    process_steps = process_steps.sort_values(
        ["_numeric_sequence", "_workbook_order"], kind="stable"
    )

    definitions = []
    for _, row in process_steps.iterrows():
        excel_row = int(row["_excel_row"])
        definitions.append(
            {
                "sequence": row["Sequence"],
                "application_id": _positive_integer(
                    row["Application"], "Application", excel_row
                ),
                "module": _required_text(row["Module"], "Module"),
                "batch_limit": _parse_batch_limit(row["BatchCount"], excel_row),
                "excel_row": excel_row,
            }
        )
    return definitions


def _parse_batch_limit(value: Any, excel_row: int) -> int | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None

    number = _decimal_value(value, "BatchCount", excel_row)
    if number != number.to_integral_value():
        raise ValueError(
            f"KeySteps row {excel_row} has invalid BatchCount: {value!r}; "
            "expected zero or a positive integer"
        )

    batch_limit = int(number)
    if batch_limit < 0:
        raise ValueError(
            f"KeySteps row {excel_row} has invalid BatchCount: {value!r}; "
            "expected zero or a positive integer"
        )
    return None if batch_limit == 0 else batch_limit


def _positive_integer(value: Any, name: str, excel_row: int) -> int:
    number = _decimal_value(value, name, excel_row)
    if number != number.to_integral_value() or number <= 0:
        raise ValueError(
            f"KeySteps row {excel_row} has invalid {name}: {value!r}; "
            "expected a positive integer"
        )
    return int(number)


def _decimal_value(value: Any, name: str, excel_row: int) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError(
            f"KeySteps row {excel_row} has invalid {name}: {value!r}"
        ) from error
    if not number.is_finite():
        raise ValueError(f"KeySteps row {excel_row} has invalid {name}: {value!r}")
    return number


def _nonnegative_integer(value: Any, name: str) -> int:
    number = _decimal_value(value, name, 0)
    if number != number.to_integral_value() or number < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(number)


def _load_process_function(module_spec: str) -> Callable[[OrqflowState], Any]:
    module_name, separator, function_name = module_spec.partition(":")
    module_name = module_name.strip()
    function_name = function_name.strip()
    if not separator or not module_name or not function_name:
        raise ValueError(
            "Process Module must use the format 'package.module:function'"
        )

    module = importlib.import_module(module_name)
    process_function = getattr(module, function_name, None)
    if not callable(process_function):
        raise TypeError(f"Configured process function is not callable: {module_spec}")
    return process_function


def _validate_result(
    result: Any,
    module_spec: str,
) -> tuple[Outcome, str | None, dict[str, Any], str | None]:
    if not isinstance(result, Mapping):
        raise TypeError(f"Process function must return a mapping: {module_spec}")

    try:
        outcome = Outcome(result["outcome"])
    except KeyError as error:
        raise ValueError("Process result is missing 'outcome'") from error
    except ValueError as error:
        raise ValueError(f"Process result has invalid outcome: {result.get('outcome')!r}") from error

    if outcome not in PROCESS_OUTCOMES:
        raise ValueError(f"Process result cannot use outcome: {outcome}")

    message_value = result.get("message")
    message = None if message_value is None else str(message_value)
    data_value = result.get("data", {})
    if not isinstance(data_value, Mapping):
        raise TypeError("Process result 'data' must be a mapping")

    next_action_value = result.get("next_action")
    next_action = None if next_action_value is None else str(next_action_value)
    return outcome, message, dict(data_value), next_action


def _cto_details_from_result(data: Mapping[str, Any]) -> str | None:
    value = data.get("cto_details")
    if value is None:
        value = data.get("CTO_Details")
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return json.dumps(value, default=str)


def _application_matches(value: Any, expected: Any) -> bool:
    try:
        return float(value) == float(expected)
    except (TypeError, ValueError):
        return str(value).strip() == str(expected).strip()


def _required_text(value: Any, name: str) -> str:
    if value is None or pd.isna(value) or not str(value).strip():
        raise ValueError(f"KeySteps {name} value is required")
    return str(value).strip()
