from __future__ import annotations

from framework.adapters import InMemoryQueue
from framework.logging_config import get_logger
from framework.state import OrqflowState


def initialize_framework(state: OrqflowState) -> OrqflowState:
    state["queue"] = InMemoryQueue()
    get_logger("services.framework").debug("Queue initialized: %s", state["queue"].transactions)
    return state
