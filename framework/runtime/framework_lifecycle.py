from __future__ import annotations

from framework.logging_config import get_logger
from framework.state import OrqflowState


def initialize_framework(state: OrqflowState) -> OrqflowState:
    get_logger("runtime.framework").info("Framework lifecycle initialized")
    return state
