from __future__ import annotations

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility
    from enum import Enum

    class StrEnum(str, Enum):
        pass
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
