from __future__ import annotations

from framework.state import OrqflowState


def cleanup_execution(state: OrqflowState) -> OrqflowState:
    driver = state.get("driver")
    if driver is not None:
        driver.stop()
    return state
