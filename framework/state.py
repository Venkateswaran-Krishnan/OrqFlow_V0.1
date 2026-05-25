from __future__ import annotations

from typing import Any, TypedDict


class OrqflowState(TypedDict, total=False):
    config: dict[str, Any]
    config_context: dict[str, str]
    runtime_config: dict[str, Any]
    repo: Any
    driver: Any
    queue: Any
    queue_db: Any
    key_steps: Any
    logs: list[str]
