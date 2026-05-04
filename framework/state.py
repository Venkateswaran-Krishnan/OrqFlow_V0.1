from __future__ import annotations

from typing import Any, TypedDict


class OrqflowState(TypedDict, total=False):
    execution_config: dict[str, Any]
    process_config: dict[str, Any]
    logging_config: dict[str, Any]
    runtime_config: dict[str, Any]
    repo: Any
    driver: Any
    queue: Any
    init_module: Any
    process_module: Any
    process_module_app: str
    automation_steps: list[dict[str, Any]]
    logs: list[str]
