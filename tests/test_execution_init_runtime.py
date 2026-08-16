from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from framework.results import Outcome
from framework.runtime.execution_init_runtime import initialize_execution


class ExecutionInitRuntimeTests(unittest.TestCase):
    def test_startup_selects_existing_first_application_without_reset(self) -> None:
        reset = Mock()
        state = self._state("STARTUP", reset)

        self._initialize_with_module(state, reset)

        reset.assert_not_called()
        self.assertEqual(13, state["runtime_config"]["active_application_id"])
        self.assertEqual(2, state["runtime_config"]["session_batch_count"])

    def test_batch_completion_resets_current_app_and_selects_next_app(self) -> None:
        reset = Mock()
        state = self._state("BATCH_COMPLETE", reset)

        self._initialize_with_module(state, reset)

        reset.assert_called_once_with(state)
        self.assertEqual(14, state["runtime_config"]["active_application_id"])
        self.assertEqual(1, state["runtime_config"]["active_process_step_index"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])
        self.assertFalse(state["runtime_config"]["application_logged_in"])

    def test_application_switch_uses_current_application_reset_hook(self) -> None:
        reset = Mock()
        state = self._state("STARTUP", reset)
        state["runtime_config"]["next_action"] = "APP_SWITCH"

        self._initialize_with_module(state, reset)

        reset.assert_called_once_with(state)
        self.assertEqual("APP_SWITCH", state["runtime_config"]["execution_init_reason"])
        self.assertEqual(14, state["runtime_config"]["active_application_id"])

    def test_retry_preserves_transaction_and_application_but_resets_session(self) -> None:
        reset = Mock()
        state = self._state("RETRY", reset)
        transaction = state["runtime_config"]["txn"]

        self._initialize_with_module(state, reset)

        reset.assert_called_once_with(state)
        self.assertIs(transaction, state["runtime_config"]["txn"])
        self.assertEqual(13, state["runtime_config"]["active_application_id"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])

    def test_missing_reset_hook_is_optional(self) -> None:
        reset = Mock()
        state = self._state("BATCH_COMPLETE", reset)
        state["key_steps"] = state["key_steps"].loc[
            state["key_steps"]["State"] == "PROCESS_TRANSACTION"
        ]

        initialize_execution(state)

        self.assertEqual(14, state["runtime_config"]["active_application_id"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])

    def test_reset_hook_exception_becomes_system_exception(self) -> None:
        reset = Mock(side_effect=RuntimeError("Application close failed"))
        state = self._state("BATCH_COMPLETE", reset)

        self._initialize_with_module(state, reset)

        self.assertEqual(Outcome.SYSTEM_EXCEPTION, state["runtime_config"]["last_status"])
        self.assertEqual("Application close failed", state["runtime_config"]["last_error"])
        self.assertEqual("END", state["runtime_config"]["next_action"])
        self.assertEqual(13, state["runtime_config"]["active_application_id"])
        self.assertEqual(2, state["runtime_config"]["session_batch_count"])

    @staticmethod
    def _initialize_with_module(state: dict, reset: Mock) -> None:
        module = types.ModuleType("test_execution_init_module")
        module.reset_application = reset
        with patch.dict(sys.modules, {"test_execution_init_module": module}):
            initialize_execution(state)

    @staticmethod
    def _state(reason: str, _reset: Mock) -> dict:
        return {
            "runtime_config": {
                "execution_init_reason": reason,
                "next_action": None,
                "active_process_step_index": 0,
                "active_application_id": 13,
                "active_batch_limit": 2,
                "session_batch_count": 2,
                "application_logged_in": True,
                "txn": {"queue_id": 101, "queue_application_details": 13},
                "last_status": None,
                "last_error": None,
            },
            "process_steps": [
                {
                    "sequence": 10,
                    "application_id": 13,
                    "module": "project.process:run",
                    "batch_limit": 2,
                    "excel_row": 2,
                },
                {
                    "sequence": 20,
                    "application_id": 14,
                    "module": "project.process:run",
                    "batch_limit": 3,
                    "excel_row": 3,
                },
            ],
            "key_steps": pd.DataFrame(
                [
                    {
                        "Sequence": 5,
                        "State": "EXECUTION_INIT",
                        "Application": 13,
                        "Module": "test_execution_init_module:reset_application",
                    },
                    {
                        "Sequence": 10,
                        "State": "PROCESS_TRANSACTION",
                        "Application": 13,
                        "Module": "project.process:run",
                    },
                ]
            ),
            "logs": [],
        }


if __name__ == "__main__":
    unittest.main()
