from __future__ import annotations

import importlib
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

import pandas as pd

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.state import OrqflowState


LOGIN_APPLICATION_STATE = "LOGIN_APPLICATION"


def login_application(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.application")
    if runtime.get("application_logged_in"):
        logger.info("Application login skipped; existing session will be reused")
        logger.debug(
            "Application login state: application_logged_in=%s",
            runtime.get("application_logged_in"),
        )
        return state

    try:
        application_id = _transaction_application_id(runtime)
        module_spec = _select_login_module(state, application_id)
        if module_spec is None:
            logger.info("Application login hook skipped; no matching KeySteps entry")
            logger.debug(
                "Application login hook lookup: state=%s, application_id=%s",
                LOGIN_APPLICATION_STATE,
                application_id,
            )
        else:
            logger.info("Application login hook started")
            logger.debug(
                "Application login hook details: application_id=%s, module=%s",
                application_id,
                module_spec,
            )
            login_function = _load_login_function(module_spec)
            login_function(state)
            logger.info("Application login hook completed")

        runtime["application_logged_in"] = True
        logger.info("Application login completed")
        logger.debug(
            "Application login state: application_id=%s, application_logged_in=%s",
            application_id,
            runtime["application_logged_in"],
        )
    except Exception as error:
        logger.exception("Application login failed")
        runtime["application_logged_in"] = False
        runtime["last_status"] = Outcome.SYSTEM_EXCEPTION
        runtime["last_error"] = str(error)
        runtime["last_message"] = None
        runtime["last_result"] = {}
        runtime["next_action"] = None

    return state


def _transaction_application_id(runtime: Mapping[str, Any]) -> Any:
    transaction = runtime.get("txn")
    if not isinstance(transaction, Mapping):
        raise ValueError("No active queue transaction is available for application login")

    application_id = transaction.get("queue_application_details")
    if application_id is None or not str(application_id).strip():
        raise ValueError("Queue transaction has no application ID for application login")
    return application_id


def _select_login_module(state: OrqflowState, application_id: Any) -> str | None:
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
        if str(row["State"]).strip().upper() != LOGIN_APPLICATION_STATE:
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
            f"KeySteps {LOGIN_APPLICATION_STATE} Module is required for Application "
            f"{application_id}"
        )
    return str(module_value).strip()


def _load_login_function(module_spec: str) -> Callable[[OrqflowState], Any]:
    module_name, separator, function_name = module_spec.partition(":")
    module_name = module_name.strip()
    function_name = function_name.strip()
    if not separator or not module_name or not function_name:
        raise ValueError(
            "Application login Module must use the format 'package.module:function'"
        )

    module = importlib.import_module(module_name)
    login_function = getattr(module, function_name, None)
    if not callable(login_function):
        raise TypeError(
            f"Configured application login function is not callable: {module_spec}"
        )
    return login_function


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

