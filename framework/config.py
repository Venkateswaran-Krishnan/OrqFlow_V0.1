from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "retry_count": 0,
    "batch_count": 0,
    "wait_count": 0,
    "txn": None,
    "last_status": None,
    "last_error": None,
    "next_action": None,
}


def load_initial_state(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).resolve()
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    process_config = dict(raw["process_config"])
    for key in ("object_repo_path", "init_module", "process_module", "automation_steps"):
        process_config[key] = _resolve(path.parent, process_config[key])

    logging_config = dict(raw.get("logging_config", raw.get("logging", {})))
    if "log_file" in logging_config:
        logging_config["log_file"] = _resolve(path.parent, logging_config["log_file"])

    return {
        "execution_config": raw.get("execution_config", {}),
        "process_config": process_config,
        "logging_config": logging_config,
        "runtime_config": dict(DEFAULT_RUNTIME_CONFIG),
        "logs": [],
    }


def _resolve(base: Path, value: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        return str(candidate)
    return str((base / candidate).resolve())
