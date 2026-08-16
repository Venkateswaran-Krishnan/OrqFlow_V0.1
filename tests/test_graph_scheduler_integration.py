from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from framework.graph import build_graph
from framework.results import Outcome


class SimulatedQueue:
    def __init__(self) -> None:
        self.pending = {
            13: ["13-A", "13-B", "13-C"],
            14: ["14-A", "14-B"],
        }
        self.completed: list[str] = []

    def has_eligible_transactions(self) -> bool:
        return any(self.pending.values())

    def mark_success(self, txn: dict) -> None:
        self.completed.append(txn["case_id"])

    def mark_skipped(self, txn: dict, reason: str | None) -> None:
        raise AssertionError("No simulated transaction should be skipped")

    def mark_failed(self, txn: dict, reason: str | None) -> None:
        raise AssertionError("No simulated transaction should fail")


class GraphSchedulerIntegrationTests(unittest.TestCase):
    def test_compiled_graph_processes_batches_across_applications(self) -> None:
        queue = SimulatedQueue()
        fetch_order: list[tuple[int, str]] = []

        def initialize_framework(state: dict) -> dict:
            state["queue"] = queue
            state["process_steps"] = [
                {
                    "sequence": 10,
                    "application_id": 13,
                    "module": "simulated:process",
                    "batch_limit": 2,
                    "excel_row": 2,
                },
                {
                    "sequence": 20,
                    "application_id": 14,
                    "module": "simulated:process",
                    "batch_limit": 1,
                    "excel_row": 3,
                },
            ]
            state["key_steps"] = pd.DataFrame(
                [
                    {
                        "Sequence": 10,
                        "State": "PROCESS_TRANSACTION",
                        "Application": 13,
                        "Module": "simulated:process",
                    },
                    {
                        "Sequence": 20,
                        "State": "PROCESS_TRANSACTION",
                        "Application": 14,
                        "Module": "simulated:process",
                    },
                ]
            )
            runtime = state["runtime_config"]
            runtime.update(
                {
                    "active_process_step_index": 0,
                    "active_application_id": 13,
                    "active_batch_limit": 2,
                    "session_batch_count": 0,
                    "execution_init_reason": "STARTUP",
                    "master_queue_run_count": 0,
                    "master_queue_last_run_at": None,
                    "retry_count": 0,
                    "wait_count": 0,
                    "txn": None,
                    "last_status": None,
                    "last_error": None,
                    "next_action": None,
                }
            )
            return state

        def get_next_transaction(state: dict) -> dict:
            runtime = state["runtime_config"]
            application_id = runtime["active_application_id"]
            pending = queue.pending[application_id]
            if not pending:
                runtime["txn"] = None
                runtime["last_status"] = Outcome.NO_TRANSACTION
                runtime["next_action"] = None
                return state

            case_id = pending.pop(0)
            fetch_order.append((application_id, case_id))
            runtime["txn"] = {
                "queue_id": len(fetch_order),
                "case_id": case_id,
                "queue_application_details": application_id,
            }
            runtime["last_status"] = Outcome.SUCCESS
            runtime["next_action"] = "PROCESS"
            return state

        def process_transaction(state: dict) -> dict:
            state["runtime_config"]["last_status"] = Outcome.SUCCESS
            state["runtime_config"]["next_action"] = None
            return state

        initial_state = {
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
            "runtime_config": {},
            "logs": [],
        }

        with (
            patch("framework.nodes.initialize_framework", initialize_framework),
            patch("framework.nodes.get_next_transaction", get_next_transaction),
            patch("framework.nodes.login_application_runtime", lambda state: state),
            patch("framework.nodes.execute_process_transaction", process_transaction),
        ):
            result = build_graph().invoke(initial_state)

        self.assertEqual(
            [
                (13, "13-A"),
                (13, "13-B"),
                (14, "14-A"),
                (13, "13-C"),
                (14, "14-B"),
            ],
            fetch_order,
        )
        self.assertEqual(
            ["13-A", "13-B", "14-A", "13-C", "14-B"],
            queue.completed,
        )
        self.assertEqual("END", result["runtime_config"]["next_action"])


if __name__ == "__main__":
    unittest.main()
