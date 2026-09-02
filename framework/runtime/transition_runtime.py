from __future__ import annotations

import time

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.runtime.process_runtime import (
    is_session_batch_complete,
    record_finalized_transaction,
)
from framework.runtime.queue_runtime import master_queue_interval_hours
from framework.state import OrqflowState


def resolve_transition(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    outcome = Outcome(runtime["last_status"])
    txn = runtime.get("txn")
    requested_action = runtime.get("next_action")
    logger = get_logger("runtime.transition")
    logger.debug(
        "Transition input: outcome=%s, queue_id=%s, retry_count=%s, "
        "batch_count=%s, wait_count=%s, requested_action=%s",
        outcome.value,
        txn.get("queue_id") if isinstance(txn, dict) else None,
        runtime.get("retry_count"),
        runtime.get("batch_count"),
        runtime.get("wait_count"),
        requested_action,
    )

    if outcome == Outcome.SUCCESS:
        state["queue"].mark_success(
            txn,
            runtime.get("last_message"),
            runtime.get("cto_details"),
        )
        record_finalized_transaction(state)
        runtime["retry_count"] = 0
        runtime["txn"] = None
        runtime["next_action"] = next_after_finalized_transaction(state)
        logger.info("Successful transaction transition completed")
        return state

    if outcome == Outcome.BUSINESS_EXCEPTION:
        state["queue"].mark_skipped(
            txn,
            runtime.get("last_error"),
            runtime.get("cto_details"),
        )
        record_finalized_transaction(state)
        runtime["retry_count"] = 0
        runtime["txn"] = None
        runtime["next_action"] = next_after_finalized_transaction(state)
        logger.info("Business-exception transaction transition completed")
        return state

    if outcome == Outcome.SYSTEM_EXCEPTION:
        if txn is None:
            runtime["retry_count"] = 0
            runtime["next_action"] = "END"
            logger.info("System-exception transition ended without an active transaction")
            return state

        if runtime.get("retry_count", 0) < _execution_config(state).get("retry_limit", 0):
            runtime["retry_count"] = runtime.get("retry_count", 0) + 1
            runtime["next_action"] = "RETRY"
            logger.info("System-exception retry selected")
            return state

        state["queue"].mark_failed(
            txn,
            runtime.get("last_error"),
            runtime.get("cto_details"),
        )
        record_finalized_transaction(state)
        runtime["retry_count"] = 0
        runtime["txn"] = None
        runtime["next_action"] = next_after_finalized_transaction(state)
        logger.info("Failed transaction transition completed")
        return state

    if outcome == Outcome.NO_TRANSACTION:
        runtime["txn"] = None
        if state["queue"].has_eligible_transactions():
            runtime["execution_init_reason"] = "APP_SWITCH"
            runtime["next_action"] = "APP_SWITCH"
            logger.info("Application switch selected; another application has eligible work")
            return state

        if can_wait_for_transaction(state):
            runtime["wait_count"] = runtime.get("wait_count", 0) + 1
            runtime["next_action"] = "GET_TRANSACTION"
            wait_seconds = _execution_config(state).get("wait_seconds", 0)
            logger.info("No-transaction wait selected")
            logger.debug(
                "No transaction wait details: wait_seconds=%s, application_id=%s, "
                "wait_count=%s, wait_limit=%s",
                wait_seconds,
                runtime.get("active_application_id"),
                runtime.get("wait_count"),
                _execution_config(state).get("wait_limit", 0),
            )
            if wait_seconds:
                time.sleep(wait_seconds)
            return state

        runtime["execution_init_reason"] = "BATCH_COMPLETE"
        runtime["next_action"] = "BATCH_COMPLETE"
        logger.info("Application session completion selected; no eligible transaction remains")
        return state

    runtime["next_action"] = "END"
    logger.info("Transition ended")
    return state


def clear_process_runtime(state: OrqflowState) -> None:
    state.pop("process_module", None)
    state.pop("process_module_app", None)


def next_after_finalized_transaction(state: OrqflowState) -> str:
    runtime = state["runtime_config"]
    if runtime.get("next_action") == "APP_SWITCH":
        clear_process_runtime(state)
        runtime["execution_init_reason"] = "APP_SWITCH"
        return "APP_SWITCH"
    if is_session_batch_complete(state):
        runtime["execution_init_reason"] = "BATCH_COMPLETE"
        return "BATCH_COMPLETE"
    return "GET_TRANSACTION"


def next_after_success(state: OrqflowState) -> str:
    return next_after_finalized_transaction(state)


def can_wait_for_transaction(state: OrqflowState) -> bool:
    execution_config = _execution_config(state)
    runtime = state["runtime_config"]
    if not execution_config.get("wait_enabled"):
        return False
    return runtime.get("wait_count", 0) < execution_config.get("wait_limit", 0)


def has_periodic_master_queue(state: OrqflowState) -> bool:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    return settings.get("masterbot") is True and master_queue_interval_hours(state) is not None


def _execution_config(state: OrqflowState) -> dict:
    return state.get("config", {}).get("execution_config", {})
