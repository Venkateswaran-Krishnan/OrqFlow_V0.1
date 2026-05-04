from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from framework.logging_config import get_logger, trace_event
from framework.results import Outcome, StepResult, success
from framework.state import OrqflowState


REQUIRED_COLUMNS = {"order", "phase", "keyword", "source", "function_name"}


class BusinessException(Exception):
    """Expected transaction-level failure that should not trigger system retry."""


def load_automation_steps(path: str | Path) -> list[dict[str, Any]]:
    steps_path = Path(path).resolve()
    get_logger("steps").debug("Loading automation steps from %s", steps_path)
    with steps_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Automation steps file is missing columns: {sorted(missing)}")
        steps = [_normalize_row(row) for row in reader]
    return sorted(steps, key=lambda step: step["order"])


def run_phase_steps(state: OrqflowState, phase: str) -> StepResult:
    phase_steps = [step for step in state.get("automation_steps", []) if step["phase"] == phase]
    get_logger("steps").debug("Phase '%s' steps: %s", phase, phase_steps)
    for step in phase_steps:
        _log(state, f"STEP_START:{phase}:{step['keyword']}")
        result = run_step(state, step)
        _log(state, f"STEP_END:{phase}:{step['keyword']}:{result['outcome']}")
        if result["outcome"] != Outcome.SUCCESS:
            return result
    return success(f"{phase} steps completed")


def run_step(state: OrqflowState, step: dict[str, Any]) -> StepResult:
    module = _get_source_module(state, step["source"])
    function = getattr(module, step["function_name"], None)
    if function is None:
        get_logger("steps").error("Missing step function. Step: %s", step)
        return {
            "outcome": Outcome.SYSTEM_EXCEPTION,
            "message": f"Function '{step['function_name']}' not found in {step['source']} module",
        }

    try:
        get_logger("steps").debug("Running step function '%s' with parameters %s", step["function_name"], step.get("parameters", {}))
        raw_result = function(state, **step.get("parameters", {}))
    except BusinessException as exc:
        get_logger("steps").warning("Business exception in step '%s': %s", step["keyword"], exc)
        return {"outcome": Outcome.BUSINESS_EXCEPTION, "message": str(exc)}
    except Exception as exc:
        get_logger("steps").exception("System exception in step '%s'", step["keyword"])
        return {"outcome": Outcome.SYSTEM_EXCEPTION, "message": str(exc)}

    return normalize_result(raw_result)


def normalize_result(raw_result: Any) -> StepResult:
    if raw_result is None:
        return success()
    if isinstance(raw_result, dict):
        return {
            "outcome": Outcome(raw_result.get("outcome", Outcome.SUCCESS)),
            "message": raw_result.get("message"),
            "data": raw_result.get("data", {}),
            "next_action": raw_result.get("next_action"),
        }
    if isinstance(raw_result, Outcome):
        return {"outcome": raw_result}
    if isinstance(raw_result, str):
        return {"outcome": Outcome(raw_result)}
    raise TypeError(f"Unsupported step result type: {type(raw_result).__name__}")


def _normalize_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "order": int(row["order"]),
        "phase": row["phase"].strip(),
        "keyword": row["keyword"].strip(),
        "source": row["source"].strip(),
        "function_name": row["function_name"].strip(),
        "parameters": _parse_parameters(row.get("parameters", "")),
        "on_error": (row.get("on_error") or "").strip() or None,
    }


def _parse_parameters(value: str) -> dict[str, Any]:
    value = value.strip()
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Step parameters must be a JSON object")
    return parsed


def _get_source_module(state: OrqflowState, source: str):
    if source == "init":
        return state["init_module"]
    if source == "process":
        return state["process_module"]
    raise ValueError(f"Unknown step source: {source}")


def _log(state: OrqflowState, event: str) -> None:
    trace_event(state, event, logging.INFO)
