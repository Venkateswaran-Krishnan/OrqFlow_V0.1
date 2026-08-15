from __future__ import annotations

import importlib
from collections.abc import Mapping
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
        module_spec = _required_text(selected_step["Module"], "Module")
        sequence = selected_step["Sequence"]

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
        runtime["next_action"] = None

    return state


def _select_process_step(state: OrqflowState, application_id: Any) -> Mapping[str, Any]:
    key_steps = state.get("key_steps")
    if not isinstance(key_steps, pd.DataFrame):
        raise ValueError("KeySteps data is not loaded")

    required_columns = {"Sequence", "State", "Application", "Module"}
    missing_columns = sorted(required_columns.difference(key_steps.columns))
    if missing_columns:
        raise ValueError(
            "KeySteps is missing required column(s): " + ", ".join(missing_columns)
        )

    states = key_steps["State"].astype(str).str.strip().str.upper()
    applications = key_steps["Application"].map(
        lambda value: _application_matches(value, application_id)
    )
    matching_steps = key_steps.loc[(states == PROCESS_STATE) & applications].copy()
    if matching_steps.empty:
        raise ValueError(
            f"No {PROCESS_STATE} step found for Application {application_id}"
        )

    matching_steps["_numeric_sequence"] = pd.to_numeric(
        matching_steps["Sequence"], errors="raise"
    )
    selected_step = matching_steps.sort_values(
        "_numeric_sequence", kind="stable"
    ).iloc[0]
    return selected_step


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


def _application_matches(value: Any, expected: Any) -> bool:
    try:
        return float(value) == float(expected)
    except (TypeError, ValueError):
        return str(value).strip() == str(expected).strip()


def _required_text(value: Any, name: str) -> str:
    if value is None or pd.isna(value) or not str(value).strip():
        raise ValueError(f"KeySteps {name} value is required")
    return str(value).strip()
