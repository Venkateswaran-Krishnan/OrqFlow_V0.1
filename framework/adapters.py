from __future__ import annotations

from pathlib import Path
from typing import Any


class BrowserDriver:
    def __init__(self) -> None:
        self.started = False
        self.restart_count = 0

    def start(self) -> None:
        self.started = True

    def restart(self) -> None:
        self.restart_count += 1
        self.stop()
        self.start()

    def stop(self) -> None:
        self.started = False


class ObjectRepository:
    def __init__(self, base_path: str, app: str) -> None:
        self.base_path = Path(base_path)
        self.app = app
        self.cache: dict[str, Any] = {}


class InMemoryQueue:
    def __init__(self, transactions: list[dict[str, Any]] | None = None) -> None:
        self.transactions = transactions or [{"id": "demo-1", "status": "READY"}]

    def fetch_next(self) -> dict[str, Any] | None:
        for txn in self.transactions:
            if txn.get("status") == "READY":
                txn["status"] = "IN_PROGRESS"
                return txn
        return None

    def mark_success(self, txn: dict[str, Any]) -> None:
        txn["status"] = "SUCCESS"

    def mark_skipped(self, txn: dict[str, Any], reason: str | None) -> None:
        txn["status"] = "SKIPPED"
        txn["reason"] = reason

    def mark_failed(self, txn: dict[str, Any], reason: str | None) -> None:
        txn["status"] = "FAILED"
        txn["reason"] = reason
