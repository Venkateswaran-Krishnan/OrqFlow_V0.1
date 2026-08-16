from __future__ import annotations

import importlib.util
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
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
        application_id = self.state["runtime_config"].get("active_application_id")
        if application_id is None:
            raise ValueError("runtime_config.active_application_id is required")
        cursor = self.db.connection.execute(
            self.db.queries["fetch_next_transaction"],
            [queue_config["eligible_status"], application_id],
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

    def has_eligible_transactions(self) -> bool:
        cursor = self.db.connection.execute(
            self.db.queries["fetch_any_eligible_transaction"],
            [_queue_config(self.state)["eligible_status"]],
        )
        return cursor.fetchone() is not None

    def mark_success(self, txn: dict) -> None:
        self._mark_final(txn, "mark_transaction_success", _queue_config(self.state)["success_status"], None)

    def mark_skipped(self, txn: dict, reason: str | None) -> None:
        self._mark_final(txn, "mark_transaction_skipped", _queue_config(self.state)["skipped_status"], reason)

    def mark_failed(self, txn: dict, reason: str | None) -> None:
        self._mark_final(txn, "mark_transaction_failed", _queue_config(self.state)["failed_status"], reason)

    def _mark_final(self, txn: dict, query_name: str, status: str, reason: str | None) -> None:
        if txn is None:
            return
        logger = get_logger("runtime.queue")
        self.db.connection.execute(
            self.db.queries[query_name],
            [status, reason, reason, reason, reason, txn["queue_id"]],
        )
        self.db.connection.commit()
        txn["queue_processing_status"] = status
        txn["queue_bot_comment"] = reason
        logger.info("Queue transaction status updated")
        logger.debug(
            "Queue transaction status details: queue_id=%s, status=%s, reason=%s",
            txn["queue_id"],
            status,
            reason,
        )


def create_master_queue(state: OrqflowState) -> OrqflowState:
    logger = get_logger("runtime.queue")
    if not _is_master_queue_enabled(state):
        logger.info("Master queue creation skipped; masterbot is disabled")
        logger.debug("Master queue loading skipped")
        return state

    try:
        if not is_master_queue_due(state):
            runtime = state["runtime_config"]
            logger.info("Master queue creation skipped; configured schedule is not due")
            logger.debug(
                "Master queue schedule details: run_count=%s, last_run_at=%s, interval_hours=%s",
                runtime.get("master_queue_run_count"),
                runtime.get("master_queue_last_run_at"),
                master_queue_interval_hours(state),
            )
            return state

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
        record_master_queue_run(state)
        logger.info("Master queue creation completed")
        logger.debug(
            "Master queue created. Inputs inserted: %s, input rows skipped: %s, "
            "input rows failed: %s, "
            "inputs queued: %s, queue rows created: %s, queue inputs failed: %s",
            input_summary["inserted_count"],
            input_summary["skipped_count"],
            input_summary["failed_count"],
            queue_summary["queued_input_count"],
            queue_summary["created_queue_count"],
            queue_summary["failed_input_count"],
        )
        logger.debug(
            "Master queue summaries: input_summary=%s, queue_summary=%s",
            input_summary,
            queue_summary,
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
        logger.info("No transaction available")
        logger.debug(
            "No transaction details: application_id=%s, retry_count=%s, "
            "session_batch_count=%s, batch_limit=%s, wait_count=%s, "
            "master_queue_run_count=%s",
            runtime.get("active_application_id"),
            runtime.get("retry_count"),
            runtime.get("session_batch_count"),
            runtime.get("active_batch_limit"),
            runtime.get("wait_count"),
            runtime.get("master_queue_run_count"),
        )
        return state

    runtime["txn"] = txn
    runtime["batch_count"] = runtime.get("batch_count", 0) + 1
    runtime["wait_count"] = 0
    runtime["last_status"] = Outcome.SUCCESS
    runtime["last_error"] = None
    runtime["next_action"] = "PROCESS"
    logger.info("Transaction fetched and marked in progress")
    logger.debug(
        "Transaction details: queue_id=%s, input_id=%s, application_id=%s",
        txn.get("queue_id"),
        txn.get("input_id"),
        txn.get("queue_application_details"),
    )
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


def master_queue_interval_hours(state: OrqflowState) -> Decimal | None:
    settings = state.get("config", {}).get("process_config", {}).get("settings", {})
    value = settings.get("master_queue_interval_hours")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    try:
        interval = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError(
            "process_config.settings.master_queue_interval_hours must be a non-negative number"
        ) from error

    if not interval.is_finite() or interval < 0:
        raise ValueError(
            "process_config.settings.master_queue_interval_hours must be a non-negative number"
        )
    return None if interval == 0 else interval


def is_master_queue_due(state: OrqflowState, now: datetime | None = None) -> bool:
    if not _is_master_queue_enabled(state):
        return False

    interval = master_queue_interval_hours(state)
    runtime = state["runtime_config"]
    run_count = _nonnegative_runtime_integer(
        runtime.get("master_queue_run_count", 0),
        "runtime_config.master_queue_run_count",
    )
    if run_count == 0:
        return True
    if interval is None:
        return False

    last_run_at = runtime.get("master_queue_last_run_at")
    if not isinstance(last_run_at, datetime) or last_run_at.tzinfo is None:
        raise ValueError(
            "runtime_config.master_queue_last_run_at must be a timezone-aware datetime"
        )

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("Master queue schedule time must be timezone-aware")
    return current_time >= last_run_at + timedelta(hours=float(interval))


def record_master_queue_run(
    state: OrqflowState,
    now: datetime | None = None,
) -> OrqflowState:
    runtime = state["runtime_config"]
    run_count = _nonnegative_runtime_integer(
        runtime.get("master_queue_run_count", 0),
        "runtime_config.master_queue_run_count",
    )
    completed_at = now or datetime.now(timezone.utc)
    if completed_at.tzinfo is None:
        raise ValueError("Master queue completion time must be timezone-aware")

    runtime["master_queue_run_count"] = run_count + 1
    runtime["master_queue_last_run_at"] = completed_at.astimezone(timezone.utc)
    return state


def wait_for_master_queue_schedule(state: OrqflowState) -> OrqflowState:
    runtime = state["runtime_config"]
    logger = get_logger("runtime.queue")
    try:
        if master_queue_interval_hours(state) is None:
            raise ValueError("A positive master_queue_interval_hours value is required")

        wait_seconds = _positive_wait_seconds(state)
        logger.info("Waiting for the next master queue schedule check")
        logger.debug(
            "Master queue wait details: wait_seconds=%s, run_count=%s, last_run_at=%s",
            wait_seconds,
            runtime.get("master_queue_run_count"),
            runtime.get("master_queue_last_run_at"),
        )
        time.sleep(wait_seconds)
        runtime["wait_count"] = _nonnegative_runtime_integer(
            runtime.get("wait_count", 0),
            "runtime_config.wait_count",
        ) + 1
        runtime["execution_init_reason"] = "MASTER_QUEUE_REFRESH"
        runtime["next_action"] = "MASTER_QUEUE_REFRESH"
    except Exception as error:
        logger.exception("Master queue schedule wait failed")
        _set_runtime_failure(state, error)
    return state


def _nonnegative_runtime_integer(value: object, name: str) -> int:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{name} must be a non-negative integer") from error
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(number)


def _positive_wait_seconds(state: OrqflowState) -> float:
    value = state.get("config", {}).get("execution_config", {}).get("wait_seconds")
    try:
        seconds = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as error:
        raise ValueError(
            "execution_config.wait_seconds must be a positive number when periodic masterbot is enabled"
        ) from error
    if not seconds.is_finite() or seconds <= 0:
        raise ValueError(
            "execution_config.wait_seconds must be a positive number when periodic masterbot is enabled"
        )
    return float(seconds)


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
    logger = get_logger("runtime.queue")

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
        "skipped_count": 0,
        "failed_count": 0,
        "inserted_input_ids": [],
        "skipped_rows": [],
        "failed_rows": [],
    }
    for row_index, row in dataframe.iterrows():
        excel_row_number = int(row_index) + 2
        row_error = _validate_required_row_values(row, required_fields)
        if row_error is not None:
            summary["failed_rows"].append({"row": excel_row_number, "error": row_error})
            summary["failed_count"] += 1
            logger.warning("Input row rejected during validation")
            logger.debug(
                "Input row validation failure: row=%s, error=%s",
                excel_row_number,
                row_error,
            )
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
            if _is_duplicate_input_error(error, db.db_type):
                summary["skipped_rows"].append({"row": excel_row_number})
                summary["skipped_count"] += 1
                logger.info("Existing input row skipped")
                logger.debug("Existing input row skipped: row=%s", excel_row_number)
                continue
            summary["failed_rows"].append(
                {"row": excel_row_number, "error": f"DB insert failed: {error}"}
            )
            summary["failed_count"] += 1
            logger.error("Input row database insert failed", exc_info=True)
            logger.debug(
                "Input row database failure: row=%s, error=%s",
                excel_row_number,
                error,
            )
            continue
        summary["inserted_count"] += 1
        summary["inserted_input_ids"].append(cursor.lastrowid)

    return summary


def _is_duplicate_input_error(error: Exception, db_type: str) -> bool:
    if db_type == "sqlite":
        unique_error_code = getattr(sqlite3, "SQLITE_CONSTRAINT_UNIQUE", 2067)
        return isinstance(error, sqlite3.IntegrityError) and (
            getattr(error, "sqlite_errorcode", None) == unique_error_code
            or "UNIQUE constraint failed" in str(error)
        )
    if db_type == "mysql":
        return getattr(error, "errno", None) == 1062
    return False


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
    logger = get_logger("runtime.queue")
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
            logger.error("Queue creation failed for an input", exc_info=True)
            logger.debug(
                "Queue creation failure: input_id=%s, error=%s",
                input_id,
                error,
            )
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

