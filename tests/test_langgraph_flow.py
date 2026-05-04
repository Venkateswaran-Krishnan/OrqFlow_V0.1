from pathlib import Path
import unittest

from framework.graph import run_graph


class LangGraphFlowTests(unittest.TestCase):
    def test_demo_graph_marks_transaction_success(self):
        config_path = Path(__file__).resolve().parents[1] / "examples" / "config.json"

        final_state = run_graph(config_path)

        self.assertEqual(final_state["queue"].transactions[0]["status"], "SUCCESS")
        self.assertIn("NODE:FRAMEWORK_INIT", final_state["logs"])
        self.assertIn("NODE:EXECUTION_INIT", final_state["logs"])
        self.assertIn("NODE:TRANSITION_HUB:SUCCESS", final_state["logs"])
        self.assertIn("PROCESS_FUNC:submit_transaction", final_state["logs"])
        self.assertFalse(final_state["driver"].started)


if __name__ == "__main__":
    unittest.main()
