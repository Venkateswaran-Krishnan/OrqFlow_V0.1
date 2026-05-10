from __future__ import annotations

from typing import Any, TypedDict


class OrqflowState(TypedDict, total=False):
    config: dict[str, Any]
    runtime_config: dict[str, Any]
    repo: Any
    driver: Any
    queue: Any
    logs: list[str]
