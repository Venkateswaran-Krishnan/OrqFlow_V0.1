from __future__ import annotations

import json
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "first_run": True,
    "queue_initialized": False,
    "application_logged_in": False,
    "retry_count": 0,
    "batch_count": 0,
    "active_process_step_index": None,
    "active_application_id": None,
    "active_batch_limit": None,
    "session_batch_count": 0,
    "execution_init_reason": "STARTUP",
    "master_queue_run_count": 0,
    "master_queue_last_run_at": None,
    "wait_count": 0,
    "txn": None,
    "last_status": None,
    "last_error": None,
    "next_action": None,
}

DEFAULT_BOOTSTRAP_PATH = "bootstrap.json"


def load_initial_state(config_path: str | Path = DEFAULT_BOOTSTRAP_PATH) -> dict[str, Any]:
    path = Path(config_path).resolve()
    raw, _config_base, context = load_config(path)

    config = dict(raw)
    logging_config = dict(config.get("logging_config", config.get("logging", {})))
    if "log_file" in logging_config:
        log_base = Path(context["bot_config_dir"])
        logging_config["log_file"] = _prepare_log_file(log_base, logging_config)
        config["logging_config"] = logging_config

    return {
        "config": config,
        "config_context": context,
        "runtime_config": dict(DEFAULT_RUNTIME_CONFIG),
        "logs": [],
    }


def load_config(config_path: str | Path) -> tuple[dict[str, Any], Path, dict[str, str]]:
    path = Path(config_path).resolve()
    if path.is_dir():
        return _load_layered_config(path)

    if _is_bootstrap_config(path):
        return _load_bootstrap_config(path)

    if _is_project_config(path):
        return _load_layered_config(path.parent, project_config_path=path)

    return _load_json(path), path.parent, {"share_root": str(path.parent)}


def _load_bootstrap_config(path: Path) -> tuple[dict[str, Any], Path, dict[str, str]]:
    bootstrap = _load_json(path)
    share_root = bootstrap["share_root"]
    project = bootstrap["project"]
    shared_root_path = _resolve(path.parent, share_root)
    project_config_dir = Path(shared_root_path) / "config" / project
    return _load_layered_config(project_config_dir, context={"share_root": shared_root_path})


def _load_layered_config(
    project_config_dir: Path,
    project_config_path: Path | None = None,
    context: dict[str, str] | None = None,
) -> tuple[dict[str, Any], Path, dict[str, str]]:
    project_config_path = project_config_path or project_config_dir / "project_config.json"
    global_config_path = project_config_dir.parent / "global_config.json"
    machine_name = get_machine_name()
    bot_config_dir = project_config_dir / machine_name
    bot_config_path = bot_config_dir / "bot_config.json"
    context = dict(context or {"share_root": str(project_config_dir.parent.parent)})
    context["project_config_dir"] = str(project_config_dir)
    context["bot_config_dir"] = str(bot_config_dir)

    merged: dict[str, Any] = {}
    for candidate in (global_config_path, project_config_path, bot_config_path):
        if candidate.exists():
            merged = _merge_config(merged, _load_json(candidate))

    if not merged:
        raise FileNotFoundError(f"No config files found for project config directory: {project_config_dir}")

    return merged, project_config_dir, context


def get_machine_name() -> str:
    return (
        os.environ.get("COMPUTERNAME")
        or os.environ.get("HOSTNAME")
        or platform.node()
    )


def _is_project_config(path: Path) -> bool:
    return path.name == "project_config.json" and path.parent.parent.name == "config"


def _is_bootstrap_config(path: Path) -> bool:
    if path.name == "bootstrap.json":
        return True

    if not path.exists() or path.suffix.lower() != ".json":
        return False

    config = _load_json(path)
    return "share_root" in config and "project" in config


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if _is_empty(value):
            continue

        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
            continue

        merged[key] = value

    return merged


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _prepare_log_file(base: Path, logging_config: dict[str, Any]) -> str:
    log_file = _resolve(base, logging_config["log_file"])
    if logging_config.get("timestamp_file"):
        log_file = _add_timestamp(log_file)
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    return log_file


def _add_timestamp(path: str) -> str:
    log_path = Path(path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(log_path.with_name(f"{log_path.stem}_{timestamp}{log_path.suffix}"))


def _resolve(base: Path, value: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        return str(candidate)
    return str((base / candidate).resolve())
