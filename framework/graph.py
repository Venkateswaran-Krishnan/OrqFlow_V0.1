from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from framework.config import DEFAULT_BOOTSTRAP_PATH, load_initial_state
from framework.logging_config import configure_logging, get_logger, shutdown_logging
from framework.nodes import (
    end,
    execution_init,
    framework_init,
    get_transaction,
    login_application,
    master_queue_creator,
    process_transaction,
    route_after_framework_init,
    route_after_execution_init,
    route_after_get,
    route_after_master_queue_creator,
    route_after_transition,
    transition_hub,
)
from framework.state import OrqflowState


def build_graph():
    graph = StateGraph(OrqflowState)

    graph.add_node("framework_init", framework_init)
    graph.add_node("execution_init", execution_init)
    graph.add_node("master_queue_creator", master_queue_creator)
    graph.add_node("get_transaction", get_transaction)
    graph.add_node("login_application", login_application)
    graph.add_node("process_transaction", process_transaction)
    graph.add_node("transition_hub", transition_hub)
    graph.add_node("end", end)

    graph.set_entry_point("framework_init")
    graph.add_conditional_edges(
        "framework_init",
        route_after_framework_init,
        {
            "execution_init": "execution_init",
            "end": "end",
        },
    )
    graph.add_conditional_edges(
        "execution_init",
        route_after_execution_init,
        {
            "master_queue_creator": "master_queue_creator",
            "get_transaction": "get_transaction",
        },
    )
    graph.add_conditional_edges(
        "master_queue_creator",
        route_after_master_queue_creator,
        {
            "get_transaction": "get_transaction",
            "end": "end",
        },
    )
    graph.add_conditional_edges(
        "get_transaction",
        route_after_get,
        {
            "login_application": "login_application",
            "transition_hub": "transition_hub",
        },
    )
    graph.add_edge("login_application", "process_transaction")
    graph.add_edge("process_transaction", "transition_hub")
    graph.add_conditional_edges(
        "transition_hub",
        route_after_transition,
        {
            "execution_init": "execution_init",
            "get_transaction": "get_transaction",
            "end": "end",
        },
    )
    graph.add_edge("end", END)

    return graph.compile()


def run_graph(config_path: str | Path = DEFAULT_BOOTSTRAP_PATH) -> dict[str, Any]:
    app = build_graph()
    configure_logging()
    logger = get_logger("graph")
    try:
        state = load_initial_state(config_path)
        configure_logging(state.get("config", {}).get("logging_config"))
        logger = get_logger("graph")
        _log_effective_config(state)
        logger.debug("Initial state: %s", state)
        return app.invoke(state)
    except Exception:
        logger.exception("Unhandled framework execution error")
        raise
    finally:
        shutdown_logging()


def _log_effective_config(state: dict[str, Any]) -> None:
    logger = get_logger("config")
    logger.debug(
        "Effective config: %s",
        json.dumps(state.get("config", {}), indent=2, sort_keys=True, default=str),
    )
