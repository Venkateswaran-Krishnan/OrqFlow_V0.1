from __future__ import annotations

import importlib.util
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from framework.logging_config import get_logger
from framework.results import Outcome
from framework.state import OrqflowState


GENERATED_TBL_INPUT_COLUMNS = {"ID", "Process", "Input_Identifier"}


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
            [status, reason, reason, reason, reason, txn["queue_id"]],
        )
        self.db.connection.commit()
        txn["queue_processing_status"] = status
        txn["queue_bot_comment"] = reason


def create_master_queue(state: OrqflowState) -> OrqflowState:
    logger = get_logger("runtime.queue")
    if not _is_master_queue_enabled(state):
        logger.debug("Master queue loading skipped")
        return state

    try:
        dataframe = _load_input_dataframe(state)
        process_id = _process_id(state)
        application_ids = _extract_distinct_process_applications(state)
        db = _active_queue_db(state)
        _validate_application_ids(db, application_ids)

        input_summary = _insert_input_dataframe(state, dataframe)
        queue_summary = _create_queues_for_eligible_inputs(
            state,
            process_id,
            application_ids,
        )
        state["runtime_config"]["input_load_summary"] = input_summary
        state["runtime_config"]["queue_creation_summary"] = queue_summary
        logger.info(
            "Master queue created. Inputs inserted: %s, input rows failed/skipped: %s, "
            "inputs queued: %s, queue rows created: %s, queue inputs failed: %s",
            input_summary["inserted_count"],
            input_summary["failed_count"],
            queue_summary["queued_input_count"],
            queue_summary["created_queue_count"],
            queue_summary["failed_input_count"],
        )
    except Exception as error:
        logger.exception("Master queue input loading failed")
        _set_runtime_failure(state, error)
    return state


def get_next_transaction(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.queue")
    try:
        _ensure_queue_initialized(state)
        txn = state["queue"].fetch_next()
    except Exception as error:
        logger.exception("Get transaction failed")
        runtime["txn"] = None
        runtime["last_status"] = Outcome.SYSTEM_EXCEPTION
        runtime["last_error"] = str(error)
        runtime["next_action"] = None
        return state

    if txn is None:
        runtime["txn"] = None
        runtime["last_status"] = Outcome.NO_TRANSACTION
        runtime["next_action"] = None
        logger.debug("No transaction available. Runtime: %s", runtime)
        return state

    runtime["txn"] = txn
    runtime["batch_count"] = runtime.get("batch_count", 0) + 1
    runtime["wait_count"] = 0
    runtime["last_status"] = Outcome.SUCCESS
    runtime["last_error"] = None
    runtime["next_action"] = "PROCESS"
    logger.debug("Transaction fetched: %s", txn)
    return state


def _ensure_queue_initialized(state: OrqflowState) -> None:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.queue")
    if runtime.get("queue_initialized"):
        logger.debug("Queue already initialized; reusing existing queue")
        return

    logger.info("Queue initialization started")
    if state.get("queue_db") is None:
        raise ValueError("state['queue_db'] is required for queue initialization")

    state["queue"] = DatabaseQueue(state)
    logger.info("Database-backed queue initialized")
    runtime["queue_initialized"] = True
    logger.info("Queue initialization completed")


def _is_master_queue_enabled(state: OrqflowState) -> bool:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    return settings.get("masterbot") is True


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


def _load_input_dataframe(state: OrqflowState) -> Any:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    source = str(settings.get("Queue") or "").strip().lower()
    if source == "excel":
        return _load_excel_dataframe(state, _resolve_queue_file_path(state))
    if source == "api":
        return _load_api_dataframe(state)
    raise ValueError(f"Unsupported queue input source: {settings.get('Queue')}")


def _load_excel_dataframe(state: OrqflowState, excel_path: Path) -> Any:
    excel_module_path = Path(state["config_context"]["share_root"]) / "common" / "excel.py"
    spec = importlib.util.spec_from_file_location("shared_excel", excel_module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Excel utility could not be loaded: {excel_module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_excel_dataframe(excel_path)


def _load_api_dataframe(state: OrqflowState) -> Any:
    api_module_path = Path(state["config_context"]["share_root"]) / "common" / "api.py"
    spec = importlib.util.spec_from_file_location("shared_api", api_module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"API utility could not be loaded: {api_module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    return module.read_api_dataframe(settings.get("ApiConfig") or {})


def _insert_input_dataframe(state: OrqflowState, dataframe: Any) -> dict[str, Any]:
    process_id = _process_id(state)
    db = _active_queue_db(state)

    db_schema = _tbl_input_schema(db)
    db_columns = set(db_schema)
    required_fields = _required_input_fields(db_schema)
    missing_columns = required_fields.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(
            "Input source missing required tbl_input field(s): "
            + ", ".join(sorted(missing_columns))
        )
    if "Process" not in db_columns:
        raise ValueError("tbl_input.Process column is required")

    insertable_columns = [
        column
        for column in dataframe.columns
        if column in db_columns and column not in GENERATED_TBL_INPUT_COLUMNS
    ]
    insertable_columns.append("Process")
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

    summary: dict[str, Any] = {
        "inserted_count": 0,
        "failed_count": 0,
        "inserted_input_ids": [],
        "failed_rows": [],
    }
    for row_index, row in dataframe.iterrows():
        excel_row_number = int(row_index) + 2
        row_error = _validate_required_row_values(row, required_fields)
        if row_error is not None:
            summary["failed_rows"].append({"row": excel_row_number, "error": row_error})
            summary["failed_count"] += 1
            continue

        values = []
        for column in insertable_columns:
            if column == "Process":
                values.append(process_id)
            elif column == "Input_Identifier":
                values.append(f"{process_id}_{row['Case_ID']}")
            else:
                values.append(_normalize_db_value(row[column]))

        try:
            cursor = db.connection.execute(sql, values)
            db.connection.commit()
        except Exception as error:
            db.connection.rollback()
            summary["failed_rows"].append(
                {"row": excel_row_number, "error": f"DB insert failed: {error}"}
            )
            summary["failed_count"] += 1
            continue
        summary["inserted_count"] += 1
        summary["inserted_input_ids"].append(cursor.lastrowid)

    return summary


def _extract_distinct_process_applications(state: OrqflowState) -> list[int]:
    dataframe = state.get("key_steps")
    if dataframe is None:
        raise ValueError("state['key_steps'] is required for master queue creation")

    required_columns = {"State", "Sequence", "Application"}
    missing_columns = required_columns.difference(dataframe.columns)
    if missing_columns:
        raise ValueError(
            "KeySteps missing required column(s): " + ", ".join(sorted(missing_columns))
        )

    process_rows: list[tuple[Decimal, int, int]] = []
    for workbook_order, (_, row) in enumerate(dataframe.iterrows()):
        state_name = str(_normalize_db_value(row["State"]) or "").strip().upper()
        if state_name != "PROCESS_TRANSACTION":
            continue

        sequence = _numeric_key_step_value(row["Sequence"], "Sequence", workbook_order + 2)
        application = _positive_application_id(row["Application"], workbook_order + 2)
        process_rows.append((sequence, workbook_order, application))

    if not process_rows:
        raise ValueError("KeySteps has no PROCESS_TRANSACTION rows")

    process_rows.sort(key=lambda item: (item[0], item[1]))
    distinct_applications: list[int] = []
    seen: set[int] = set()
    for _, _, application in process_rows:
        if application not in seen:
            seen.add(application)
            distinct_applications.append(application)
    return distinct_applications


def _numeric_key_step_value(value: Any, column: str, excel_row: int) -> Decimal:
    normalized = _normalize_db_value(value)
    if normalized is None or isinstance(normalized, bool):
        raise ValueError(f"KeySteps row {excel_row} has invalid {column}: {value!r}")
    try:
        number = Decimal(str(normalized).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(
            f"KeySteps row {excel_row} has invalid {column}: {value!r}"
        ) from None
    if not number.is_finite():
        raise ValueError(f"KeySteps row {excel_row} has invalid {column}: {value!r}")
    return number


def _positive_application_id(value: Any, excel_row: int) -> int:
    number = _numeric_key_step_value(value, "Application", excel_row)
    if number != number.to_integral_value() or number <= 0:
        raise ValueError(
            f"KeySteps row {excel_row} has invalid Application: {value!r}; "
            "expected a positive integer tbl_application.ID"
        )
    return int(number)


def _validate_application_ids(db: Any, application_ids: list[int]) -> None:
    rows = db.connection.execute(db.queries["select_application_ids"]).fetchall()
    valid_ids = {int(_row_value(row, "ID", 0)) for row in rows}
    missing_ids = [
        application_id
        for application_id in application_ids
        if application_id not in valid_ids
    ]
    if missing_ids:
        raise ValueError(
            "KeySteps Application ID(s) not found in tbl_application: "
            + ", ".join(str(value) for value in missing_ids)
        )


def _select_eligible_inputs(state: OrqflowState, process_id: str) -> list[Any]:
    db = _active_queue_db(state)
    return db.connection.execute(
        db.queries["select_inputs_for_queue_creation"],
        [process_id],
    ).fetchall()


def _create_queue_set_for_input(
    state: OrqflowState,
    input_id: int,
    process_id: str,
    application_ids: list[int],
    queue_status: str,
) -> int:
    db = _active_queue_db(state)
    for application_id in application_ids:
        db.connection.execute(
            db.queries["insert_tbl_queue"],
            [input_id, application_id, queue_status],
        )

    cursor = db.connection.execute(
        db.queries["mark_input_queue_created"],
        [queue_status, input_id, process_id],
    )
    if cursor.rowcount != 1:
        raise RuntimeError(
            f"Expected to mark one tbl_input row as queue created for input ID {input_id}; "
            f"updated {cursor.rowcount}"
        )
    db.connection.commit()
    return len(application_ids)


def _create_queues_for_eligible_inputs(
    state: OrqflowState,
    process_id: str,
    application_ids: list[int],
) -> dict[str, Any]:
    db = _active_queue_db(state)
    eligible_inputs = _select_eligible_inputs(state, process_id)
    summary: dict[str, Any] = {
        "distinct_application_count": len(application_ids),
        "eligible_input_count": len(eligible_inputs),
        "queued_input_count": 0,
        "created_queue_count": 0,
        "failed_input_count": 0,
        "failed_inputs": [],
    }
    queue_status = _queue_config(state)["eligible_status"]

    for row in eligible_inputs:
        input_id = int(_row_value(row, "ID", 0))
        try:
            created_count = _create_queue_set_for_input(
                state,
                input_id,
                process_id,
                application_ids,
                queue_status,
            )
        except Exception as error:
            db.connection.rollback()
            summary["failed_input_count"] += 1
            summary["failed_inputs"].append({"input_id": input_id, "error": str(error)})
            continue
        summary["queued_input_count"] += 1
        summary["created_queue_count"] += created_count

    return summary


def _active_queue_db(state: OrqflowState) -> Any:
    db = state.get("queue_db")
    if db is None or getattr(db, "connection", None) is None:
        raise ValueError("state['queue_db'] with an active connection is required")
    return db


def _row_value(row: Any, name: str, index: int) -> Any:
    if hasattr(row, "keys"):
        return row[name]
    if isinstance(row, dict):
        return row[name]
    return row[index]


def _tbl_input_columns(db: Any) -> set[str]:
    return set(_tbl_input_schema(db))


def _tbl_input_schema(db: Any) -> dict[str, dict[str, Any]]:
    query = db.queries["tbl_input_columns"]
    rows = db.connection.execute(query).fetchall()
    columns: dict[str, dict[str, Any]] = {}
    for row in rows:
        if db.db_type == "sqlite":
            columns[row["name"]] = {
                "required": bool(row["notnull"]),
                "primary_key": bool(row["pk"]),
            }
        elif db.db_type == "mysql":
            field = row["Field"] if isinstance(row, dict) else row[0]
            nullable = row["Null"] if isinstance(row, dict) else row[2]
            key = row["Key"] if isinstance(row, dict) else row[3]
            columns[field] = {
                "required": str(nullable).upper() == "NO",
                "primary_key": str(key).upper() == "PRI",
            }
        else:
            raise ValueError(f"Unsupported queue database type: {db.db_type}")
    return columns


def _required_input_fields(schema: dict[str, dict[str, Any]]) -> set[str]:
    return {
        column
        for column, metadata in schema.items()
        if metadata.get("required") and column not in GENERATED_TBL_INPUT_COLUMNS
    }


def _process_id(state: OrqflowState) -> str:
    value = state.get("config", {}).get("process_config", {}).get("Process_ID")
    if value is None or str(value).strip() == "":
        raise ValueError("process_config.Process_ID is required")
    return str(value).strip()


def _validate_required_row_values(row: Any, required_fields: set[str]) -> str | None:
    missing = [
        field
        for field in sorted(required_fields)
        if _is_blank_value(_normalize_db_value(row[field]))
    ]
    if missing:
        return "Missing required value(s): " + ", ".join(missing)
    return None


def _is_blank_value(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


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

