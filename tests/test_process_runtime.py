from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

from framework.results import Outcome, success
from framework.runtime.process_runtime import execute_process_transaction


class ProcessRuntimeTests(unittest.TestCase):
    def test_matching_module_is_executed_and_result_is_applied(self) -> None:
        module = types.ModuleType("test_process_module")
        module.run_process = lambda state: success("Processed", output="result.json")
        state = self._state("test_process_module:run_process")

        with patch.dict(sys.modules, {"test_process_module": module}):
            result = execute_process_transaction(state)

        self.assertIs(result, state)
        self.assertEqual(Outcome.SUCCESS, state["runtime_config"]["last_status"])
        self.assertIsNone(state["runtime_config"]["last_error"])
        self.assertEqual("Processed", state["runtime_config"]["last_message"])
        self.assertEqual(
            {"output": "result.json"}, state["runtime_config"]["last_result"]
        )
        self.assertFalse(state["runtime_config"]["first_run"])

    def test_module_exception_becomes_system_exception(self) -> None:
        module = types.ModuleType("failing_process_module")

        def fail(_state):
            raise RuntimeError("OCR service unavailable")

        module.run_process = fail
        state = self._state("failing_process_module:run_process")

        with patch.dict(sys.modules, {"failing_process_module": module}):
            execute_process_transaction(state)

        self.assertEqual(
            Outcome.SYSTEM_EXCEPTION, state["runtime_config"]["last_status"]
        )
        self.assertEqual(
            "OCR service unavailable", state["runtime_config"]["last_error"]
        )
        self.assertIsNone(state["runtime_config"]["next_action"])

    def test_returned_business_exception_logs_its_message(self) -> None:
        module = types.ModuleType("business_process_module")
        module.run_process = lambda state: {
            "outcome": Outcome.BUSINESS_EXCEPTION,
            "message": "Required document is missing",
            "data": {},
            "next_action": None,
        }
        state = self._state("business_process_module:run_process")

        with patch.dict(sys.modules, {"business_process_module": module}):
            with self.assertLogs("framework.runtime.process", level="DEBUG") as logs:
                execute_process_transaction(state)

        output = "\n".join(logs.output)
        self.assertIn("returned a business exception", output)
        self.assertIn("Required document is missing", output)

    def test_missing_application_step_becomes_system_exception(self) -> None:
        state = self._state("unused.module:run_process")
        state["runtime_config"]["txn"]["queue_application_details"] = 99

        execute_process_transaction(state)

        self.assertEqual(
            Outcome.SYSTEM_EXCEPTION, state["runtime_config"]["last_status"]
        )
        self.assertIn("Application 99", state["runtime_config"]["last_error"])

    @staticmethod
    def _state(module_spec: str) -> dict:
        return {
            "runtime_config": {
                "txn": {"queue_application_details": 12},
                "first_run": True,
                "last_status": None,
                "last_error": None,
                "next_action": None,
            },
            "key_steps": pd.DataFrame(
                [
                    {
                        "Sequence": 2,
                        "State": "PROCESS_TRANSACTION",
                        "Application": 12,
                        "Module": module_spec,
                    }
                ]
            ),
        }


if __name__ == "__main__":
    unittest.main()
