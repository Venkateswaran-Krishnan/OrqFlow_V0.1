from __future__ import annotations

from framework.logging_config import get_logger
from framework.state import OrqflowState


def cleanup_execution(state: OrqflowState) -> OrqflowState:
    logger = get_logger("runtime.cleanup")
    logger.info("Execution cleanup started")

    driver = state.get("driver")
    queue_db = state.get("queue_db")
    logger.debug(
        "Cleanup resources: driver_present=%s, queue_db_present=%s",
        driver is not None,
        queue_db is not None,
    )

    if driver is not None:
        driver.stop()
        logger.info("Browser driver stopped")

    if queue_db is not None:
        queue_db.close()
        logger.info("Queue database connection closed")

    logger.info("Execution cleanup completed")
    return state
