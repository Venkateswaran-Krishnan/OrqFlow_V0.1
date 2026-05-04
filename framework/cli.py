from __future__ import annotations

import argparse

from framework.graph import run_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Orqflow LangGraph workflow.")
    parser.add_argument("config", help="Path to an Orqflow JSON config file.")
    args = parser.parse_args()

    run_graph(args.config)
