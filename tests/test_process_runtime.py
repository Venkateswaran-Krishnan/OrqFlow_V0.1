from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

from framework.results import Outcome, success
from framework.runtime.process_runtime import (
    activate_next_process_step,
    execute_process_transaction,
    initialize_process_scheduler,
    is_session_batch_complete,
    load_process_steps,
    record_finalized_transaction,
)


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
        self.assertIsNone(state["runtime_config"]["cto_details"])
        self.assertFalse(state["runtime_config"]["first_run"])

    def test_cto_details_result_is_stored_for_transition(self) -> None:
        module = types.ModuleType("cto_process_module")
        module.run_process = lambda state: success(
            "Processed",
            CTO_Details={"overall_status": "Success"},
        )
        state = self._state("cto_process_module:run_process")

        with patch.dict(sys.modules, {"cto_process_module": module}):
            execute_process_transaction(state)

        self.assertEqual(
            '{"overall_status": "Success"}',
            state["runtime_config"]["cto_details"],
        )

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
        self.assertIsNone(state["runtime_config"]["cto_details"])

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

    def test_process_steps_are_ordered_and_batch_count_is_parsed(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = pd.DataFrame(
            [
                self._step(sequence=30, application=14, batch_count=3),
                self._step(sequence=10, application=12, batch_count=None),
                self._step(sequence=20, application=13, batch_count=0),
            ]
        )

        steps = load_process_steps(state)

        self.assertEqual([10, 20, 30], [step["sequence"] for step in steps])
        self.assertEqual([12, 13, 14], [step["application_id"] for step in steps])
        self.assertEqual([None, None, 3], [step["batch_limit"] for step in steps])

    def test_blank_batch_count_means_all(self) -> None:
        for batch_count in (None, "", "   "):
            with self.subTest(batch_count=batch_count):
                state = self._state("test_process_module:run_process")
                state["key_steps"] = pd.DataFrame(
                    [self._step(sequence=2, application=12, batch_count=batch_count)]
                )

                steps = load_process_steps(state)

                self.assertIsNone(steps[0]["batch_limit"])

    def test_invalid_batch_count_is_rejected(self) -> None:
        for batch_count in (-1, 1.5, "not-a-number"):
            with self.subTest(batch_count=batch_count):
                state = self._state("test_process_module:run_process")
                state["key_steps"] = pd.DataFrame(
                    [self._step(sequence=2, application=12, batch_count=batch_count)]
                )

                with self.assertRaisesRegex(ValueError, "BatchCount"):
                    load_process_steps(state)

    def test_batch_count_column_is_required(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = state["key_steps"].drop(columns=["BatchCount"])

        with self.assertRaisesRegex(ValueError, "BatchCount"):
            load_process_steps(state)

    def test_scheduler_initializes_ordered_steps_and_active_session_state(self) -> None:
        state = self._state("test_process_module:run_process")
        state["runtime_config"]["session_batch_count"] = 99
        state["key_steps"] = pd.DataFrame(
            [
                self._step(sequence=20, application=14, batch_count=0),
                self._step(sequence=10, application=13, batch_count=2),
            ]
        )

        result = initialize_process_scheduler(state)

        self.assertIs(result, state)
        self.assertEqual([13, 14], [step["application_id"] for step in state["process_steps"]])
        self.assertEqual(0, state["runtime_config"]["active_process_step_index"])
        self.assertEqual(13, state["runtime_config"]["active_application_id"])
        self.assertEqual(2, state["runtime_config"]["active_batch_limit"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])

    def test_scheduler_initializes_unlimited_active_batch(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = pd.DataFrame(
            [self._step(sequence=10, application=13, batch_count=None)]
        )

        initialize_process_scheduler(state)

        self.assertIsNone(state["runtime_config"]["active_batch_limit"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])

    def test_finalized_transactions_increment_session_count_and_reach_limit(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = pd.DataFrame(
            [self._step(sequence=10, application=13, batch_count=2)]
        )
        initialize_process_scheduler(state)

        record_finalized_transaction(state)
        self.assertEqual(1, state["runtime_config"]["session_batch_count"])
        self.assertFalse(is_session_batch_complete(state))

        record_finalized_transaction(state)
        self.assertEqual(2, state["runtime_config"]["session_batch_count"])
        self.assertTrue(is_session_batch_complete(state))

    def test_unlimited_batch_never_completes_by_count(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = pd.DataFrame(
            [self._step(sequence=10, application=13, batch_count=0)]
        )
        initialize_process_scheduler(state)

        for _ in range(10):
            record_finalized_transaction(state)

        self.assertEqual(10, state["runtime_config"]["session_batch_count"])
        self.assertFalse(is_session_batch_complete(state))

    def test_advancing_switches_application_and_resets_session_count(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = pd.DataFrame(
            [
                self._step(sequence=10, application=13, batch_count=2),
                self._step(sequence=20, application=14, batch_count=3),
            ]
        )
        initialize_process_scheduler(state)
        record_finalized_transaction(state)

        activate_next_process_step(state)

        self.assertEqual(1, state["runtime_config"]["active_process_step_index"])
        self.assertEqual(14, state["runtime_config"]["active_application_id"])
        self.assertEqual(3, state["runtime_config"]["active_batch_limit"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])

    def test_advancing_single_step_reactivates_same_app_and_resets_count(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = pd.DataFrame(
            [self._step(sequence=10, application=13, batch_count=2)]
        )
        initialize_process_scheduler(state)
        record_finalized_transaction(state)

        activate_next_process_step(state)

        self.assertEqual(0, state["runtime_config"]["active_process_step_index"])
        self.assertEqual(13, state["runtime_config"]["active_application_id"])
        self.assertEqual(2, state["runtime_config"]["active_batch_limit"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])

    def test_advancing_last_step_cycles_to_first(self) -> None:
        state = self._state("test_process_module:run_process")
        state["key_steps"] = pd.DataFrame(
            [
                self._step(sequence=10, application=13, batch_count=2),
                self._step(sequence=20, application=14, batch_count=3),
            ]
        )
        initialize_process_scheduler(state)
        activate_next_process_step(state)
        record_finalized_transaction(state)

        activate_next_process_step(state)

        self.assertEqual(0, state["runtime_config"]["active_process_step_index"])
        self.assertEqual(13, state["runtime_config"]["active_application_id"])
        self.assertEqual(0, state["runtime_config"]["session_batch_count"])

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
                        "BatchCount": 0,
                        "Application": 12,
                        "Module": module_spec,
                    }
                ]
            ),
        }

    @staticmethod
    def _step(sequence: int, application: int, batch_count: object) -> dict:
        return {
            "Sequence": sequence,
            "State": "PROCESS_TRANSACTION",
            "BatchCount": batch_count,
            "Application": application,
            "Module": "test_process_module:run_process",
        }


if __name__ == "__main__":
    unittest.main()
