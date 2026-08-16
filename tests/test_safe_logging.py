from __future__ import annotations

import unittest

from framework.results import Outcome
from framework.runtime.queue_runtime import get_next_transaction
from framework.runtime.transition_runtime import resolve_transition


SENSITIVE_VALUE = "sensitive-customer-value"


class StubQueue:
    def __init__(self) -> None:
        self.successful_transactions = []

    def fetch_next(self) -> dict:
        return {
            "queue_id": 7,
            "input_id": 11,
            "queue_application_details": 13,
            "customer_data": SENSITIVE_VALUE,
        }

    def mark_success(self, transaction: dict) -> None:
        self.successful_transactions.append(transaction)


class EmptyQueue:
    def fetch_next(self) -> None:
        return None


class SafeLoggingTests(unittest.TestCase):
    def test_transaction_debug_log_uses_safe_identifiers_only(self) -> None:
        state = {
            "runtime_config": {
                "queue_initialized": True,
                "batch_count": 0,
                "wait_count": 0,
            },
            "queue": StubQueue(),
        }

        with self.assertLogs("framework.runtime.queue", level="DEBUG") as logs:
            get_next_transaction(state)

        output = "\n".join(logs.output)
        self.assertIn("queue_id=7", output)
        self.assertIn("input_id=11", output)
        self.assertIn("application_id=13", output)
        self.assertNotIn(SENSITIVE_VALUE, output)

    def test_transition_debug_log_does_not_include_runtime_or_result_data(self) -> None:
        queue = StubQueue()
        state = {
            "runtime_config": {
                "last_status": Outcome.SUCCESS,
                "txn": {"queue_id": 7, "customer_data": SENSITIVE_VALUE},
                "last_result": {"ocr_result": SENSITIVE_VALUE},
                "retry_count": 0,
                "batch_count": 1,
                "wait_count": 0,
                "next_action": None,
            },
            "config": {
                "execution_config": {
                    "batch_enabled": True,
                    "batch_limit": 1,
                }
            },
            "queue": queue,
        }

        with self.assertLogs("framework.runtime.transition", level="DEBUG") as logs:
            resolve_transition(state)

        output = "\n".join(logs.output)
        self.assertIn("outcome=SUCCESS", output)
        self.assertIn("queue_id=7", output)
        self.assertIn("batch_count=1", output)
        self.assertNotIn(SENSITIVE_VALUE, output)

    def test_no_transaction_debug_log_uses_safe_runtime_fields_only(self) -> None:
        state = {
            "runtime_config": {
                "queue_initialized": True,
                "active_application_id": 13,
                "retry_count": 0,
                "session_batch_count": 2,
                "active_batch_limit": 3,
                "wait_count": 1,
                "master_queue_run_count": 1,
                "last_result": {"ocr_result": SENSITIVE_VALUE},
                "last_error": SENSITIVE_VALUE,
                "txn": None,
            },
            "queue": EmptyQueue(),
        }

        with self.assertLogs("framework.runtime.queue", level="DEBUG") as logs:
            get_next_transaction(state)

        output = "\n".join(logs.output)
        self.assertIn("application_id=13", output)
        self.assertIn("session_batch_count=2", output)
        self.assertIn("batch_limit=3", output)
        self.assertNotIn(SENSITIVE_VALUE, output)
        self.assertNotIn("last_result", output)


if __name__ == "__main__":
    unittest.main()
