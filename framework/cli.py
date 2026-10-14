from __future__ import annotations

import argparse

from framework.config import DEFAULT_BOOTSTRAP_PATH
from framework.graph import run_graph
from framework.results import Outcome


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Orqflow LangGraph workflow.")
    parser.add_argument(
        "config",
        nargs="?",
        default=DEFAULT_BOOTSTRAP_PATH,
        help="Path to a bootstrap JSON file, config JSON file, or project config directory.",
    )
    args = parser.parse_args()

    state = run_graph(args.config)
    return int(state.get("runtime_config", {}).get("last_status") == Outcome.SYSTEM_EXCEPTION)
