from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict


class Outcome(StrEnum):
    SUCCESS = "SUCCESS"
    BUSINESS_EXCEPTION = "BUSINESS_EXCEPTION"
    SYSTEM_EXCEPTION = "SYSTEM_EXCEPTION"
    NO_TRANSACTION = "NO_TRANSACTION"
    END = "END"


class StepResult(TypedDict, total=False):
    outcome: str
    message: str | None
    data: dict[str, Any]
    next_action: str | None


def success(message: str | None = None, **data: Any) -> StepResult:
    return {"outcome": Outcome.SUCCESS, "message": message, "data": data}
