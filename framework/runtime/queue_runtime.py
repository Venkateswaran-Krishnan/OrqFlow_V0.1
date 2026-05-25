from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.state import OrqflowState


MANDATORY_TBL_INPUT_COLUMNS = {
    "Processor",
    "Process",
    "Chargeback_Date",
    "Case_Json",
    "Case_ID",
}


class InMemoryQueue:
    def __init__(self, transactions: list[dict] | None = None) -> None:
        self.transactions = transactions or [{"id": "demo-1", "status": "READY"}]

    def fetch_next(self) -> dict | None:
        for txn in self.transactions:
            if txn.get("status") == "READY":
                txn["status"] = "IN_PROGRESS"
                return txn
        return None

    def mark_success(self, txn: dict) -> None:
        txn["status"] = "SUCCESS"

    def mark_skipped(self, txn: dict, reason: str | None) -> None:
        txn["status"] = "SKIPPED"
        txn["reason"] = reason

    def mark_failed(self, txn: dict, reason: str | None) -> None:
        txn["status"] = "FAILED"
        txn["reason"] = reason


class DatabaseQueue:
    def __init__(self, state: OrqflowState) -> None:
        self.state = state
        self.db = state["queue_db"]

    def fetch_next(self) -> dict | None:
        queue_config = _queue_config(self.state)
        cursor = self.db.connection.execute(
            self.db.queries["fetch_next_transaction"],
            [queue_config["eligible_status"]],
        )
        row = cursor.fetchone()
        if row is None:
            return None

        txn = _row_to_dict(row)
        self.db.connection.execute(
            self.db.queries["mark_transaction_in_progress"],
            [
                queue_config["in_progress_status"],
                _bot_name(self.state),
                txn["queue_id"],
            ],
        )
        self.db.connection.commit()
        txn["queue_processing_status"] = queue_config["in_progress_status"]
        txn["case_json"] = _parse_case_json(txn.get("input_case_json"))
        return txn

    def mark_success(self, txn: dict) -> None:
        self._mark_final(txn, "mark_transaction_success", _queue_config(self.state)["success_status"], None)

    def mark_skipped(self, txn: dict, reason: str | None) -> None:
        self._mark_final(txn, "mark_transaction_skipped", _queue_config(self.state)["skipped_status"], reason)

    def mark_failed(self, txn: dict, reason: str | None) -> None:
        self._mark_final(txn, "mark_transaction_failed", _queue_config(self.state)["failed_status"], reason)

    def _mark_final(self, txn: dict, query_name: str, status: str, reason: str | None) -> None:
        if txn is None:
            return
        self.db.connection.execute(
            self.db.queries[query_name],
            [status, reason, txn["queue_id"]],
        )
        self.db.connection.commit()
        txn["queue_processing_status"] = status
        txn["queue_bot_comment"] = reason


def create_master_queue(state: OrqflowState) -> OrqflowState:
    logger = get_logger("runtime.queue")
    if not _is_excel_master_queue_enabled(state):
        logger.debug("Excel master queue loading skipped")
        return state

    try:
        excel_path = _resolve_queue_file_path(state)
        dataframe = _load_excel_dataframe(state, excel_path)
        inserted_count = _insert_tbl_input_rows(state, dataframe)
        logger.info("Excel master queue input loaded. Rows inserted into tbl_input: %s", inserted_count)
    except Exception as error:
        logger.exception("Excel master queue input loading failed")
        _set_runtime_failure(state, error)
    return state


def get_next_transaction(state: OrqflowState) -> OrqflowState:
    _ensure_queue_initialized(state)
    txn = state["queue"].fetch_next()
    runtime = state["runtime_config"]
    if txn is None:
        runtime["txn"] = None
        runtime["last_status"] = Outcome.NO_TRANSACTION
        runtime["next_action"] = None
        get_logger("runtime.queue").debug("No transaction available. Runtime: %s", runtime)
        return state

    runtime["txn"] = txn
    runtime["batch_count"] = runtime.get("batch_count", 0) + 1
    runtime["wait_count"] = 0
    runtime["last_status"] = Outcome.SUCCESS
    runtime["last_error"] = None
    runtime["next_action"] = "PROCESS"
    get_logger("runtime.queue").debug("Transaction fetched: %s", txn)
    return state


def _ensure_queue_initialized(state: OrqflowState) -> None:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.queue")
    if runtime.get("queue_initialized"):
        logger.debug("Queue already initialized; reusing existing queue")
        return

    logger.info("Queue initialization started")
    if state.get("queue_db") is not None:
        state["queue"] = DatabaseQueue(state)
        logger.info("Database-backed queue initialized")
    else:
        state["queue"] = InMemoryQueue()
        logger.info(
            "In-memory queue initialized. Transaction count: %s",
            len(state["queue"].transactions),
        )
    runtime["queue_initialized"] = True
    logger.info("Queue initialization completed")


def _is_excel_master_queue_enabled(state: OrqflowState) -> bool:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    return (
        settings.get("masterbot") is True
        and str(settings.get("Queue") or "").strip().lower() == "excel"
    )


def _resolve_queue_file_path(state: OrqflowState) -> Path:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    raw_path = str(settings.get("QueueFileLocation") or "").strip()
    if not raw_path:
        raise ValueError("process_config.settings.QueueFileLocation is required for Excel queue loading")

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(state["config_context"]["project_config_dir"]) / candidate
    candidate = candidate.resolve()

    if not candidate.exists():
        raise FileNotFoundError(f"Excel queue file not found: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"Excel queue path is not a file: {candidate}")
    return candidate


def _load_excel_dataframe(state: OrqflowState, excel_path: Path) -> Any:
    excel_module_path = Path(state["config_context"]["share_root"]) / "common" / "excel.py"
    spec = importlib.util.spec_from_file_location("shared_excel", excel_module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Excel utility could not be loaded: {excel_module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_excel_dataframe(excel_path)


def _insert_tbl_input_rows(state: OrqflowState, dataframe: Any) -> int:
    missing_columns = MANDATORY_TBL_INPUT_COLUMNS.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(
            "Excel queue file missing mandatory tbl_input column(s): "
            + ", ".join(sorted(missing_columns))
        )

    db = state.get("queue_db")
    if db is None or getattr(db, "connection", None) is None:
        raise ValueError("state['queue_db'] with an active connection is required")

    db_columns = _tbl_input_columns(db)
    insertable_columns = [
        column
        for column in dataframe.columns
        if column in db_columns and column != "ID" and column != "Input_Identifier"
    ]
    if "Input_Identifier" in db_columns:
        insertable_columns.append("Input_Identifier")

    if not insertable_columns:
        raise ValueError("No Excel columns match tbl_input insertable columns")

    placeholders = ", ".join([db.placeholder] * len(insertable_columns))
    column_names = ", ".join(insertable_columns)
    sql = db.queries["insert_tbl_input"].format(
        columns=column_names,
        placeholders=placeholders,
    )

    inserted_count = 0
    for row_index, row in dataframe.iterrows():
        values = []
        for column in insertable_columns:
            if column == "Input_Identifier":
                values.append(f"{row['Process']}_{row['Case_ID']}")
            else:
                values.append(_normalize_db_value(row[column]))

        try:
            db.connection.execute(sql, values)
            db.connection.commit()
        except Exception as error:
            excel_row_number = int(row_index) + 2
            raise RuntimeError(f"Failed to insert Excel row {excel_row_number} into tbl_input: {error}") from error
        inserted_count += 1

    return inserted_count


def _tbl_input_columns(db: Any) -> set[str]:
    query = db.queries["tbl_input_columns"]
    rows = db.connection.execute(query).fetchall()
    columns: set[str] = set()
    for row in rows:
        if db.db_type == "sqlite":
            columns.add(row["name"])
        elif db.db_type == "mysql":
            columns.add(row["Field"] if isinstance(row, dict) else row[0])
        else:
            raise ValueError(f"Unsupported queue database type: {db.db_type}")
    return columns


def _normalize_db_value(value: Any) -> Any:
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass

    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _set_runtime_failure(state: OrqflowState, error: Exception) -> None:
    runtime = state["runtime_config"]
    runtime["last_status"] = Outcome.SYSTEM_EXCEPTION
    runtime["last_error"] = str(error)
    runtime["next_action"] = "END"


def _queue_config(state: OrqflowState) -> dict[str, str]:
    configured = state.get("config", {}).get("queue_config", {})
    return {
        "eligible_status": configured.get("eligible_status") or "Queue Created",
        "in_progress_status": configured.get("in_progress_status") or "In Processing",
        "success_status": configured.get("success_status") or "Success",
        "failed_status": configured.get("failed_status") or "Failed",
        "skipped_status": configured.get("skipped_status") or "Skipped",
    }


def _bot_name(state: OrqflowState) -> str | None:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    return settings.get("bot")


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _parse_case_json(value: Any) -> Any:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value

