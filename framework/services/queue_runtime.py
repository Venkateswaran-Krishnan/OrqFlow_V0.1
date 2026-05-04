from __future__ import annotations

import time

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.state import OrqflowState


def create_master_queue(state: OrqflowState) -> OrqflowState:
    return state


def get_next_transaction(state: OrqflowState) -> OrqflowState:
    txn = state["queue"].fetch_next()
    runtime = state["runtime_config"]
    if txn is None:
        runtime["txn"] = None
        runtime["last_status"] = Outcome.NO_TRANSACTION
        if can_wait_for_transaction(state):
            runtime["wait_count"] = runtime.get("wait_count", 0) + 1
            runtime["next_action"] = "WAIT"
            wait_seconds = state["execution_config"].get("wait_seconds", 0)
            get_logger("services.queue").debug(
                "No transaction found. Waiting %s seconds. Runtime: %s",
                wait_seconds,
                runtime,
            )
            if wait_seconds:
                time.sleep(wait_seconds)
            return state

        runtime["next_action"] = "END"
        get_logger("services.queue").debug("No transaction available. Runtime: %s", runtime)
        return state

    runtime["txn"] = txn
    runtime["batch_count"] = runtime.get("batch_count", 0) + 1
    runtime["wait_count"] = 0
    runtime["last_status"] = Outcome.SUCCESS
    runtime["last_error"] = None
    runtime["next_action"] = "PROCESS"
    get_logger("services.queue").debug("Transaction fetched: %s", txn)
    return state


def can_wait_for_transaction(state: OrqflowState) -> bool:
    execution_config = state["execution_config"]
    runtime = state["runtime_config"]
    if not execution_config.get("wait_enabled"):
        return False
    return runtime.get("wait_count", 0) < execution_config.get("wait_limit", 0)
