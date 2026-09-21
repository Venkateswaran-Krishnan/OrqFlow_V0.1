from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from framework.results import Outcome
from framework.runtime.framework_lifecycle import initialize_framework


class FrameworkLifecycleTests(unittest.TestCase):
    def test_configured_project_hook_runs_once_after_framework_resources(self) -> None:
        queue_db = Mock()
        queue_db.describe.return_value = {"adapter": "test"}
        initialize_project = Mock(
            side_effect=lambda state: state["runtime_config"].update(
                {"project_hook_ran": True}
            )
        )
        module = types.ModuleType("test_framework_init_module")
        module.initialize_project = initialize_project
        state = self._state("test_framework_init_module:initialize_project")

        with (
            patch.dict(sys.modules, {"test_framework_init_module": module}),
            patch(
                "framework.runtime.framework_lifecycle._read_key_steps",
                return_value=state["key_steps"],
            ),
            patch(
                "framework.runtime.framework_lifecycle.initialize_process_scheduler"
            ),
            patch(
                "framework.runtime.framework_lifecycle.initialize_queue_db_adapter",
                return_value=queue_db,
            ),
        ):
            initialize_framework(state)

        initialize_project.assert_called_once_with(state)
        self.assertIs(queue_db, state["queue_db"])
        self.assertTrue(state["runtime_config"]["project_hook_ran"])

    def test_blank_project_hook_is_optional(self) -> None:
        queue_db = Mock()
        state = self._state(None)

        with (
            patch(
                "framework.runtime.framework_lifecycle._read_key_steps",
                return_value=state["key_steps"],
            ),
            patch(
                "framework.runtime.framework_lifecycle.initialize_process_scheduler"
            ),
            patch(
                "framework.runtime.framework_lifecycle.initialize_queue_db_adapter",
                return_value=queue_db,
            ),
            patch("framework.runtime.framework_lifecycle.importlib.import_module") as load,
        ):
            initialize_framework(state)

        load.assert_not_called()
        self.assertIsNone(state["runtime_config"]["last_status"])

    def test_project_hook_exception_becomes_system_exception(self) -> None:
        initialize_project = Mock(side_effect=RuntimeError("Project setup failed"))
        module = types.ModuleType("test_failing_framework_init_module")
        module.initialize_project = initialize_project
        state = self._state(
            "test_failing_framework_init_module:initialize_project"
        )

        with (
            patch.dict(sys.modules, {"test_failing_framework_init_module": module}),
            patch(
                "framework.runtime.framework_lifecycle._read_key_steps",
                return_value=state["key_steps"],
            ),
            patch(
                "framework.runtime.framework_lifecycle.initialize_process_scheduler"
            ),
            patch(
                "framework.runtime.framework_lifecycle.initialize_queue_db_adapter",
                return_value=Mock(),
            ),
        ):
            initialize_framework(state)

        self.assertEqual(Outcome.SYSTEM_EXCEPTION, state["runtime_config"]["last_status"])
        self.assertEqual("Project setup failed", state["runtime_config"]["last_error"])
        self.assertEqual("END", state["runtime_config"]["next_action"])

    @staticmethod
    def _state(module_spec: str | None) -> dict:
        return {
            "config_context": {"project_config_dir": "."},
            "runtime_config": {
                "last_status": None,
                "last_error": None,
                "next_action": None,
            },
            "key_steps": pd.DataFrame(
                [
                    {
                        "Sequence": 0,
                        "State": "FRAMEWORK_INIT",
                        "Application": "Common",
                        "Module": module_spec,
                    }
                ]
            ),
        }


if __name__ == "__main__":
    unittest.main()
