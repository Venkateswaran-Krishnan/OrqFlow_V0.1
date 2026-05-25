from __future__ import annotations

from framework.state import OrqflowState


def cleanup_execution(state: OrqflowState) -> OrqflowState:
    driver = state.get("driver")
    if driver is not None:
        driver.stop()

    queue_db = state.get("queue_db")
    if queue_db is not None:
        queue_db.close()
    return state
