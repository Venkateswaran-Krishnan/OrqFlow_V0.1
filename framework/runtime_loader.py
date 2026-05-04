from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_runtime_module(path: str, module_name: str) -> ModuleType:
    module_path = Path(path).resolve()
    if not module_path.exists():
        raise FileNotFoundError(f"Runtime module not found: {module_path}")

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to import runtime module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
