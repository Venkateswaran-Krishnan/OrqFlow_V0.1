from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from framework.results import Outcome
from framework.runtime.application_runtime import login_application


class ApplicationRuntimeTests(unittest.TestCase):
    def test_matching_login_key_step_invokes_configured_module(self) -> None:
        login = Mock()
        state = self._state()

        self._login_with_module(state, login)

        login.assert_called_once_with(state)
        self.assertTrue(state["runtime_config"]["application_logged_in"])

    def test_first_matching_row_by_sequence_is_selected(self) -> None:
        first_login = Mock()
        second_login = Mock()
        state = self._state()
        state["key_steps"] = pd.DataFrame(
            [
                {
                    "Sequence": 20,
                    "State": "LOGIN_APPLICATION",
                    "Application": 13,
                    "Module": "test_login_module:second_login",
                },
                {
                    "Sequence": 10,
                    "State": "LOGIN_APPLICATION",
                    "Application": 13,
                    "Module": "test_login_module:first_login",
                },
            ]
        )
        module = types.ModuleType("test_login_module")
        module.first_login = first_login
        module.second_login = second_login

        with patch.dict(sys.modules, {"test_login_module": module}):
            login_application(state)

        first_login.assert_called_once_with(state)
        second_login.assert_not_called()

    def test_missing_matching_login_key_step_uses_placeholder_login(self) -> None:
        state = self._state()
        state["key_steps"].loc[0, "Application"] = 14

        login_application(state)

        self.assertTrue(state["runtime_config"]["application_logged_in"])
        self.assertIsNone(state["runtime_config"]["last_status"])

    def test_existing_session_does_not_invoke_login_module(self) -> None:
        login = Mock()
        state = self._state()
        state["runtime_config"]["application_logged_in"] = True

        self._login_with_module(state, login)

        login.assert_not_called()

    def test_login_hook_exception_becomes_system_exception(self) -> None:
        login = Mock(side_effect=RuntimeError("Application login failed"))
        state = self._state()

        self._login_with_module(state, login)

        self.assertFalse(state["runtime_config"]["application_logged_in"])
        self.assertEqual(Outcome.SYSTEM_EXCEPTION, state["runtime_config"]["last_status"])
        self.assertEqual("Application login failed", state["runtime_config"]["last_error"])

    @staticmethod
    def _login_with_module(state: dict, login: Mock) -> None:
        module = types.ModuleType("test_login_module")
        module.login = login
        with patch.dict(sys.modules, {"test_login_module": module}):
            login_application(state)

    @staticmethod
    def _state() -> dict:
        return {
            "runtime_config": {
                "application_logged_in": False,
                "txn": {"queue_id": 101, "queue_application_details": 13},
                "last_status": None,
                "last_error": None,
                "last_message": None,
                "last_result": {},
                "next_action": "PROCESS",
            },
            "key_steps": pd.DataFrame(
                [
                    {
                        "Sequence": 10,
                        "State": "LOGIN_APPLICATION",
                        "Application": 13,
                        "Module": "test_login_module:login",
                    }
                ]
            ),
            "logs": [],
        }


if __name__ == "__main__":
    unittest.main()
