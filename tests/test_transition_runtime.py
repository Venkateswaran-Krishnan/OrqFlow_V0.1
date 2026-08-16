from __future__ import annotations

import unittest

from framework.results import Outcome
from framework.runtime.transition_runtime import resolve_transition


class StubQueue:
    def __init__(self, eligible: bool = False) -> None:
        self.eligible = eligible
        self.successful = []
        self.skipped = []
        self.failed = []

    def has_eligible_transactions(self) -> bool:
        return self.eligible

    def mark_success(self, txn: dict) -> None:
        self.successful.append(txn)

    def mark_skipped(self, txn: dict, reason: str | None) -> None:
        self.skipped.append((txn, reason))

    def mark_failed(self, txn: dict, reason: str | None) -> None:
        self.failed.append((txn, reason))


class TransitionRuntimeTests(unittest.TestCase):
    def test_finalized_transaction_reaching_batch_limit_restarts_session(self) -> None:
        state = self._state(Outcome.SUCCESS, batch_limit=2, session_count=1)

        resolve_transition(state)

        self.assertEqual(2, state["runtime_config"]["session_batch_count"])
        self.assertEqual("BATCH_COMPLETE", state["runtime_config"]["next_action"])
        self.assertEqual("BATCH_COMPLETE", state["runtime_config"]["execution_init_reason"])
        self.assertIsNone(state["runtime_config"]["txn"])

    def test_unlimited_batch_continues_same_application(self) -> None:
        state = self._state(Outcome.SUCCESS, batch_limit=None, session_count=10)

        resolve_transition(state)

        self.assertEqual(11, state["runtime_config"]["session_batch_count"])
        self.assertEqual("GET_TRANSACTION", state["runtime_config"]["next_action"])

    def test_requested_application_switch_still_finalizes_transaction(self) -> None:
        state = self._state(Outcome.SUCCESS, batch_limit=None)
        transaction = state["runtime_config"]["txn"]
        state["runtime_config"]["next_action"] = "APP_SWITCH"

        resolve_transition(state)

        self.assertEqual([transaction], state["queue"].successful)
        self.assertEqual(1, state["runtime_config"]["session_batch_count"])
        self.assertEqual("APP_SWITCH", state["runtime_config"]["next_action"])
        self.assertIsNone(state["runtime_config"]["txn"])

    def test_retry_preserves_transaction_and_does_not_increment_batch(self) -> None:
        state = self._state(Outcome.SYSTEM_EXCEPTION, batch_limit=2, session_count=1)
        transaction = state["runtime_config"]["txn"]

        resolve_transition(state)

        self.assertIs(transaction, state["runtime_config"]["txn"])
        self.assertEqual(1, state["runtime_config"]["session_batch_count"])
        self.assertEqual(1, state["runtime_config"]["retry_count"])
        self.assertEqual("RETRY", state["runtime_config"]["next_action"])

    def test_exhausted_retry_marks_failed_and_counts_final_transaction(self) -> None:
        state = self._state(Outcome.SYSTEM_EXCEPTION, batch_limit=2, session_count=1)
        state["runtime_config"]["retry_count"] = 1

        resolve_transition(state)

        self.assertEqual(1, len(state["queue"].failed))
        self.assertEqual(2, state["runtime_config"]["session_batch_count"])
        self.assertEqual("BATCH_COMPLETE", state["runtime_config"]["next_action"])

    def test_no_transaction_switches_when_another_application_has_work(self) -> None:
        state = self._state(Outcome.NO_TRANSACTION, eligible=True)
        state["runtime_config"]["txn"] = None

        resolve_transition(state)

        self.assertEqual("APP_SWITCH", state["runtime_config"]["next_action"])
        self.assertEqual("APP_SWITCH", state["runtime_config"]["execution_init_reason"])

    def test_no_global_transaction_closes_current_session_before_end_decision(self) -> None:
        state = self._state(Outcome.NO_TRANSACTION, eligible=False)
        state["runtime_config"]["txn"] = None

        resolve_transition(state)

        self.assertEqual("BATCH_COMPLETE", state["runtime_config"]["next_action"])
        self.assertEqual("BATCH_COMPLETE", state["runtime_config"]["execution_init_reason"])

    @staticmethod
    def _state(
        outcome: Outcome,
        batch_limit: int | None = 2,
        session_count: int = 0,
        eligible: bool = False,
    ) -> dict:
        return {
            "runtime_config": {
                "last_status": outcome,
                "last_error": "failure" if outcome != Outcome.SUCCESS else None,
                "txn": {"queue_id": 7, "queue_application_details": 13},
                "retry_count": 0,
                "batch_count": 1,
                "session_batch_count": session_count,
                "active_batch_limit": batch_limit,
                "active_application_id": 13,
                "wait_count": 0,
                "next_action": None,
            },
            "config": {
                "execution_config": {
                    "retry_limit": 1,
                    "wait_enabled": False,
                    "wait_limit": 0,
                    "wait_seconds": 1,
                },
                "process_config": {
                    "settings": {
                        "masterbot": False,
                        "master_queue_interval_hours": None,
                    }
                },
            },
            "queue": StubQueue(eligible),
        }


if __name__ == "__main__":
    unittest.main()
