# SQLite Queue Backend Plan

## Current Implementation (2026-10-13)

SQLite and MySQL are implemented in `framework/runtime/queue_db.py`, with shared queue operations in `framework/runtime/queue_runtime.py`. Release `0.1.12` executes queries through managed cursors for both databases and fixes the MySQL connection-level `execute()` failure. Existing schemas must be provisioned separately.

Select the database with `queue_database.type`. SQLite uses `queue_database.sqlite_path`; MySQL uses `queue_database.host`, `port`, `database`, `username`, and `password`. Queue status names remain under `queue_config`. The original proposal below records planning history; its `queue_config.backend` and `db_path` fields were superseded by `queue_database`.

Validation: the source suite passed with 99 tests and 20 subtests, including SQLite database behavior and MySQL connector API mocks. A live MySQL run remains to be verified after installing the updated wheel in the consuming project.

Current source input preparation constructs `Case_Json` before mandatory-field validation. It merges existing JSON object fields with non-DB input columns, preserving matching DB columns separately. The completed payload is included in the validated DataFrame and inserted unchanged. Required fields derive from the live database schema; an empty constructed payload fails when `Case_Json` is `NOT NULL`. Runtime logs report preparation and validation stages without including input values or JSON payloads. The `0.1.12` wheel was rebuilt with this change on 2026-10-13; the full source suite passed with 101 tests in the project Python 3.12 environment, including MySQL connector API mocks. A live MySQL run remains unverified.

## Summary

Add SQLite as the local queue database while preserving the production DB table model. SQLite will replicate the production schema from `docs/db_Schema_Full.sql`, especially `tbl_input` and `tbl_queue`. The framework will stop using `InMemoryQueue` and route queue creation, transaction fetch, runtime updates, and final status updates through a SQLite queue adapter.

## Key Changes

- Add a SQLite adapter behind `framework/runtime/queue_runtime.py`.
- Create SQLite tables using production-compatible names and columns, including:
  - `tbl_input.Case_Json` as the main JSON input payload.
  - `tbl_queue.Case_Details` as the reference to `tbl_input.ID`.
  - `tbl_queue.Application_Details`, `Bot_Name`, `Processing_Status`, `CTO_Details`, `Evidence_Status`, `Output_tbl_Status`, `Bot_Comment`, `Dependency`, `ProcessingSTART_timestamp`, and `ProcessingEND_timestamp`.
- Masterbot queue creation will accept supplied data as a DataFrame, whether it originally came from Excel or a production API.
- Masterbot will map DataFrame rows into production-compatible `tbl_input` columns, including `Case_Json` for the complete input detail payload, then create one linked `tbl_queue` row for each distinct application in the sequenced `PROCESS_TRANSACTION` KeySteps.
- `get_transaction` will fetch the next queue row by configured statuses, prioritizing `queue_config.in_progress_status` before `queue_config.eligible_status`, join it with `tbl_input`, mark it as `In Processing`, set `ProcessingSTART_timestamp`, and expose a transaction dict containing:
  - queue fields
  - input table fields
  - parsed `Case_Json`
- `process_transaction` may return `CTO_Details` or `cto_details` in result data; process runtime stores it as `runtime_config.cto_details`. Final queue updates write that JSON string to `tbl_queue.CTO_Details` for success, skipped, and final failed transactions. `Bot_Comment` is updated separately from the result message/error reason.
- `transition_hub` will update final queue status, optional `Bot_Comment`, optional `CTO_Details`, and `ProcessingEND_timestamp`.

## Configuration

Add queue database/status config under project or global config:

```json
"queue_config": {
  "backend": "sqlite",
  "db_path": "data/orqflow.sqlite3",
  "eligible_status": "Queue Created",
  "in_progress_status": "In Processing",
  "success_status": "Success",
  "failed_status": "Failed",
  "skipped_status": "Skipped"
}
```

Status names remain configurable because production final names will be confirmed later. `In Processing` is the confirmed in-progress value. Runtime fetch must pass the in-progress and eligible values as separate SQL parameters; storing a comma-separated SQL fragment in `eligible_status` is not supported by parameterized queries.

## Test Plan

- Verify SQLite schema initialization creates production-compatible tables.
- Verify masterbot inserts DataFrame rows into `tbl_input` and creates the complete distinct-application queue set atomically for each eligible input.
- Verify `get_transaction` selects only configured in-progress or eligible rows, prioritizes in-progress rows, and updates status to `In Processing`.
- Verify fetched transaction includes `Case_Json` plus other `tbl_input` details.
- Verify transition hub writes success, failed, and skipped statuses correctly.
- Verify `python -m framework` runs with SQLite queue enabled.

## Assumptions

- `tbl_input.Case_Json` is the correct production column for full input details.
- SQLite should replicate production schema, not invent new columns.
- Status text values are configurable; only `In Processing` is currently confirmed.
- Queue fetch debug logs should include status-selection details and selected IDs, not full transaction payloads.
- DataFrame input is the common queue creation interface for both Excel and API-supplied data.
- Transaction data exposed to process code should combine `Case_Json` with the other relevant `tbl_input` columns.
