# SQLite Queue Backend Plan

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
- `get_transaction` will fetch the next eligible queue row by configured status, join it with `tbl_input`, mark it as `In Processing`, set `ProcessingSTART_timestamp`, and expose a transaction dict containing:
  - queue fields
  - input table fields
  - parsed `Case_Json`
- `process_transaction` may update queue runtime columns such as `CTO_Details`, `Evidence_Status`, `Dependency`, `Bot_Comment`, and `Output_tbl_Status`.
- `transition_hub` will update final queue status and `ProcessingEND_timestamp`.

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

Status names remain configurable because production final names will be confirmed later. `In Processing` is the confirmed in-progress value.

## Test Plan

- Verify SQLite schema initialization creates production-compatible tables.
- Verify masterbot inserts DataFrame rows into `tbl_input` and creates the complete distinct-application queue set atomically for each eligible input.
- Verify `get_transaction` selects only eligible rows and updates status to `In Processing`.
- Verify fetched transaction includes `Case_Json` plus other `tbl_input` details.
- Verify transition hub writes success, failed, and skipped statuses correctly.
- Verify `python -m framework` runs with SQLite queue enabled.

## Assumptions

- `tbl_input.Case_Json` is the correct production column for full input details.
- SQLite should replicate production schema, not invent new columns.
- Status text values are configurable; only `In Processing` is currently confirmed.
- DataFrame input is the common queue creation interface for both Excel and API-supplied data.
- Transaction data exposed to process code should combine `Case_Json` with the other relevant `tbl_input` columns.
