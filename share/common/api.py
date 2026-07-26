from __future__ import annotations

import logging
from typing import Any

try:
    from .exceptions import CommonUtilityError
except ImportError:  # Supports direct importlib loading of this file.
    import importlib.util
    from pathlib import Path

    exception_path = Path(__file__).with_name("exceptions.py")
    spec = importlib.util.spec_from_file_location("_common_exceptions", exception_path)
    if spec is None or spec.loader is None:
        raise
    exception_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exception_module)
    CommonUtilityError = exception_module.CommonUtilityError


logger = logging.getLogger("common.api")


def read_api_dataframe(config: dict[str, Any]):
    """Return API input as a pandas DataFrame once API settings are defined."""
    logger.info("API input loading requested")
    raise CommonUtilityError("API input loading is not configured yet")
