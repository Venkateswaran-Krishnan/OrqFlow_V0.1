from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from framework.nodes import route_after_execution_init
from framework.results import Outcome
from framework.runtime.queue_runtime import wait_for_master_queue_schedule


class StubQueue:
    def __init__(self, eligible: bool) -> None:
        self.eligible = eligible

    def has_eligible_transactions(self) -> bool:
        return self.eligible


class SchedulerRoutingTests(unittest.TestCase):
    def test_retry_routes_to_login_without_fetching_another_transaction(self) -> None:
        state = self._state(reason="RETRY", eligible=True)
        state["runtime_config"]["next_action"] = "RETRY"

        self.assertEqual("login_application", route_after_execution_init(state))

    def test_completed_batch_with_global_work_routes_to_get_transaction(self) -> None:
        state = self._state(reason="BATCH_COMPLETE", eligible=True)

        self.assertEqual("get_transaction", route_after_execution_init(state))

    def test_empty_nonperiodic_queue_routes_to_end(self) -> None:
        state = self._state(reason="BATCH_COMPLETE", eligible=False)

        self.assertEqual("end", route_after_execution_init(state))

    def test_empty_periodic_queue_routes_to_wait_before_interval_is_due(self) -> None:
        state = self._state(reason="BATCH_COMPLETE", eligible=False, interval=1)
        state["runtime_config"]["master_queue_run_count"] = 1
        state["runtime_config"]["master_queue_last_run_at"] = datetime.now(timezone.utc)

        self.assertEqual("master_queue_wait", route_after_execution_init(state))

    def test_due_periodic_master_queue_routes_to_creator(self) -> None:
        state = self._state(reason="MASTER_QUEUE_REFRESH", eligible=False, interval=1)
        state["runtime_config"]["master_queue_run_count"] = 1
        state["runtime_config"]["master_queue_last_run_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        )

        self.assertEqual("master_queue_creator", route_after_execution_init(state))

    def test_periodic_wait_sleeps_and_requests_schedule_refresh(self) -> None:
        state = self._state(reason="BATCH_COMPLETE", eligible=False, interval=1)
        state["config"]["execution_config"]["wait_seconds"] = "0.25"

        with patch("framework.runtime.queue_runtime.time.sleep") as sleep:
            wait_for_master_queue_schedule(state)

        sleep.assert_called_once_with(0.25)
        self.assertEqual(1, state["runtime_config"]["wait_count"])
        self.assertEqual(
            "MASTER_QUEUE_REFRESH",
            state["runtime_config"]["execution_init_reason"],
        )

    def test_periodic_wait_rejects_zero_seconds(self) -> None:
        state = self._state(reason="BATCH_COMPLETE", eligible=False, interval=1)
        state["config"]["execution_config"]["wait_seconds"] = 0

        wait_for_master_queue_schedule(state)

        self.assertEqual(Outcome.SYSTEM_EXCEPTION, state["runtime_config"]["last_status"])
        self.assertEqual("END", state["runtime_config"]["next_action"])
        self.assertIn("wait_seconds", state["runtime_config"]["last_error"])

    @staticmethod
    def _state(
        reason: str,
        eligible: bool,
        interval: object = None,
    ) -> dict:
        return {
            "runtime_config": {
                "execution_init_reason": reason,
                "next_action": reason,
                "master_queue_run_count": 1 if interval is not None else 0,
                "master_queue_last_run_at": datetime.now(timezone.utc),
                "wait_count": 0,
                "last_status": None,
                "last_error": None,
            },
            "config": {
                "execution_config": {"wait_seconds": 1},
                "process_config": {
                    "settings": {
                        "masterbot": interval is not None,
                        "master_queue_interval_hours": interval,
                    }
                },
            },
            "queue": StubQueue(eligible),
            "logs": [],
        }


if __name__ == "__main__":
    unittest.main()
