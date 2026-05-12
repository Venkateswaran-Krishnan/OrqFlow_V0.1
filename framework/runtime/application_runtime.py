from __future__ import annotations

from framework.logging_config import get_logger
from framework.state import OrqflowState


def login_application(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.application")
    if runtime.get("application_logged_in"):
        logger.debug("Application login already completed; continuing to transaction processing")
        return state

    logger.info("Application login completed")
    runtime["application_logged_in"] = True
    return state

