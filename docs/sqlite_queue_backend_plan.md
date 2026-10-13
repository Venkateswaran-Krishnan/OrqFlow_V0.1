# SQLite Queue Backend Plan

## Current Implementation (2026-10-13)

Latest source update: transaction fetch now joins `tbl_input` and filters by configured `process_config.Process_ID`, active application, and the two configured fetchable statuses. Scheduler eligibility uses the same join, process, and statuses across configured process applications; the `NO_TRANSACTION` switch check excludes the current application. Unrelated processes, unconfigured applications, and orphan queue rows cannot sustain the scheduler loop. Both MySQL and SQLite SQL were updated.

Input `Case_Number` cleanup removes all apostrophes and whitespace before validation and insertion, preserving nulls and string leading zeroes. The full source suite passed with 109 tests. MySQL coverage uses connector API mocks; no live database was verified. Release `0.1.14` includes these fixes in `dist/framework-0.1.14-py3-none-any.whl`; metadata and all 18 packaged Python files were verified against source. Build/test output is saved in `logs/wheel-build-0.1.14.log` and `logs/release-validation-0.1.14.log`. Deployment must update both the framework package and external shared SQL files. The consuming project's installed copy has not been updated.

SQLite and MySQL are implemented in `framework/runtime/queue_db.py`, with shared queue operations in `framework/runtime/queue_runtime.py`. Release `0.1.12` executes queries through managed cursors for both databases and fixes the MySQL connection-level `execute()` failure. Existing schemas must be provisioned separately.

Select the database with `queue_database.type`. SQLite uses `queue_database.sqlite_path`; MySQL uses `queue_database.host`, `port`, `database`, `username`, and `password`. Queue status names remain under `queue_config`. The original proposal below records planning history; its `queue_config.backend` and `db_path` fields were superseded by `queue_database`.

Validation: the source suite passed with 99 tests and 20 subtests, including SQLite database behavior and MySQL connector API mocks. A live MySQL run remains to be verified after installing the updated wheel in the consuming project.

Current source input preparation constructs `Case_Json` before mandatory-field validation. It merges existing JSON object fields with non-DB input columns, preserving matching DB columns separately. The completed payload is included in the validated DataFrame and inserted unchanged. Required fields derive from the live database schema; an empty constructed payload fails when `Case_Json` is `NOT NULL`. Runtime logs report preparation and validation stages without including input values or JSON payloads. The `0.1.12` wheel was rebuilt with this change on 2026-10-13; the full source suite passed with 101 tests in the project Python 3.12 environment, including MySQL connector API mocks. A live MySQL run remains unverified.

## Summary

Release update (2026-10-13): `0.1.13` includes input `Processor` mapping through `process_config.processor_mapping` after `Case_Json` construction. Matching ignores case and all whitespace. Blank, missing, and unmapped values reject their row while valid rows continue; the insert summary records failures. Mapping logs counts at `INFO`, successful row mappings at `DEBUG`, and rejected row numbers and reasons at `WARNING`. See `excel_master_queue_plan.md` for configuration and compatibility behavior. Built `dist/framework-0.1.13-py3-none-any.whl` and verified all 18 packaged Python files against source. All 103 source tests passed, including MySQL connector API mocks. Project configs remain external to the wheel; the consuming project must configure the mapping. The artifact has not been installed or deployed.

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
