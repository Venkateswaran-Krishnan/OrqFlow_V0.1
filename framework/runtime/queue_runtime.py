from __future__ import annotations

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.state import OrqflowState


class InMemoryQueue:
    def __init__(self, transactions: list[dict] | None = None) -> None:
        self.transactions = transactions or [{"id": "demo-1", "status": "READY"}]

    def fetch_next(self) -> dict | None:
        for txn in self.transactions:
            if txn.get("status") == "READY":
                txn["status"] = "IN_PROGRESS"
                return txn
        return None

    def mark_success(self, txn: dict) -> None:
        txn["status"] = "SUCCESS"

    def mark_skipped(self, txn: dict, reason: str | None) -> None:
        txn["status"] = "SKIPPED"
        txn["reason"] = reason

    def mark_failed(self, txn: dict, reason: str | None) -> None:
        txn["status"] = "FAILED"
        txn["reason"] = reason


def create_master_queue(state: OrqflowState) -> OrqflowState:
    return state


def get_next_transaction(state: OrqflowState) -> OrqflowState:
    _ensure_queue_initialized(state)
    txn = state["queue"].fetch_next()
    runtime = state["runtime_config"]
    if txn is None:
        runtime["txn"] = None
        runtime["last_status"] = Outcome.NO_TRANSACTION
        runtime["next_action"] = None
        get_logger("runtime.queue").debug("No transaction available. Runtime: %s", runtime)
        return state

    runtime["txn"] = txn
    runtime["batch_count"] = runtime.get("batch_count", 0) + 1
    runtime["wait_count"] = 0
    runtime["last_status"] = Outcome.SUCCESS
    runtime["last_error"] = None
    runtime["next_action"] = "PROCESS"
    get_logger("runtime.queue").debug("Transaction fetched: %s", txn)
    return state


def _ensure_queue_initialized(state: OrqflowState) -> None:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.queue")
    if runtime.get("queue_initialized"):
        logger.debug("Queue already initialized; reusing existing queue")
        return

    logger.info("Queue initialization started")
    state["queue"] = InMemoryQueue()
    runtime["queue_initialized"] = True
    logger.info(
        "Queue initialization completed. Transaction count: %s",
        len(state["queue"].transactions),
    )

