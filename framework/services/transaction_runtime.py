from __future__ import annotations

from framework.services.runtime_state import ensure_process_module, store_result
from framework.state import OrqflowState
from framework.steps import run_phase_steps


def process_current_transaction(state: OrqflowState) -> OrqflowState:
    ensure_process_module(state)
    result = run_phase_steps(state, "process")
    store_result(state, result)
    return state
