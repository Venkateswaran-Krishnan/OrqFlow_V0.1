# Input Loading For Master Queue Creator

## Summary

When the bot is a master bot, `master_queue_creator` loads the configured source into a canonical input DataFrame, inserts valid rows into `tbl_input`, and creates the complete application queue set for every eligible input. DB adapter initialization already belongs to `framework_init`; this behavior reuses `state["queue_db"]`.

## Trigger Conditions

Run input loading only when all are true:

- `process_config.settings.masterbot` is `true`
- `process_config.settings.Queue` names a supported source adapter

If `masterbot` is false, skip this block completely.

Schedule rules:

- `masterbot: false`: never run master queue creation.
- `masterbot: true` with blank or zero `master_queue_interval_hours`: run once per framework execution.
- `masterbot: true` with a positive interval: run at startup and again after each elapsed interval.
- Decimal hours are supported, for example `0.5` means 30 minutes.
- Negative and nonnumeric intervals are configuration errors.
- Successful runs update `runtime_config.master_queue_run_count` and the timezone-aware UTC `master_queue_last_run_at`; failed runs do not.
- When the queue is empty before a periodic run is due, `MASTER_QUEUE_WAIT` uses a positive `execution_config.wait_seconds` polling interval.

Supported source adapters:

- `Excel`: reads `QueueFileLocation` through `share/common/excel.py`.
- `API`: calls `share/common/api.py`; currently this is a configured placeholder that raises a clear error until API details are defined.

## Implementation Changes

- Keep the node thin:
  - `framework/nodes.py::master_queue_creator` continues calling `create_master_queue(state)`.
- Implement the behavior in `framework/runtime/queue_runtime.py::create_master_queue`.
- Use source adapters to create the canonical DataFrame:
  - `Excel` loads `<share_root>/common/excel.py`
  - `API` loads `<share_root>/common/api.py`
- Reuse the shared Excel utility for Excel:
  - Load `<share_root>/common/excel.py`
  - Call `read_excel_dataframe(excel_path)`
- Resolve `QueueFileLocation` only for Excel:
  - Absolute paths are used directly.
  - Relative paths are resolved from `config_context["project_config_dir"]`.
- For API, pass the full resolved `state["config"]` to `read_api_dataframe(...)`:
  - Before: `return module.read_api_dataframe(settings.get("ApiConfig") or {})`
  - After: `return module.read_api_dataframe(state.get("config", {}))`
  - This replaced the legacy `process_config.settings.ApiConfig`-only payload so API loaders can read shared process, queue, and execution configuration from one consistent config object.
- Use the already initialized DB adapter:
  - `db = state["queue_db"]`
  - Do not create a new DB connection inside master queue creator.
- Read `state["key_steps"]` before input writes:
  - Select rows whose normalized `State` is `PROCESS_TRANSACTION`.
  - Sort by numeric `Sequence`, preserving workbook order for ties.
  - Normalize `Application` as a positive integer `tbl_application.ID`.
  - Deduplicate application IDs while preserving their first sequenced occurrence.
  - Validate all distinct IDs against `tbl_application` before inserting inputs.

## Input DataFrame Validation Rules

- Excel/API sources should first be normalized into a canonical input DataFrame.
- Before JSON preparation, validation, and insertion, clean a supplied `Case_Number` in a copy of the DataFrame by removing every apostrophe (`'`) and all whitespace, including internal spaces, tabs, newlines, and Unicode whitespace. For example, ` ' 00 123 ' ` becomes `00123`. Preserve nulls and leading zeroes in strings; numeric values retain their type. A value cleaned to an empty string fails validation if the live schema requires `Case_Number`. The source DataFrame is not modified.
- Read the live `tbl_input` schema to identify DB columns, then construct `Case_Json` in a copy of the DataFrame before mandatory-column and per-row value validation.
- Merge existing `Case_Json` object fields with non-DB input columns; extra columns overwrite matching JSON keys. Matching DB columns remain separate fields in the input record.
- Validate and insert the same constructed `Case_Json` value. A required `Case_Json` can be populated from extra columns even when the source column is absent or blank. An empty constructed payload becomes `None` and fails validation if the DB requires it. Validation checks presence, not keys inside the JSON.
- After `Case_Json` construction and before mandatory validation, map the DataFrame's `Processor` names to integer IDs using `process_config.processor_mapping` in `project_config.json`. Matching removes all whitespace and ignores case in both source names and config keys. This reads the separate `Processor` column, not fields inside `Case_Json`.
- Both supplied project configs define Fiserv as `14`, Chase as `13`, Discover as `16`, and American Express as `15`:

```json
"processor_mapping": {
  "Fiserv": 14,
  "Chase": 13,
  "Discover": 16,
  "American Express": 15
}
```

- When mapping is configured, blank, missing, or unmapped `Processor` values reject only that row. A missing source `Processor` column rejects all source rows through the same per-row path. Numeric source IDs also reject unless explicitly present as mapping keys. Rejections increment `input_load_summary.failed_count` and record the row number and reason in `failed_rows`; valid rows continue.
- A configured mapping must be a non-empty JSON object with non-blank names, integer values, and no duplicate names after normalization. Invalid configuration stops input loading. If the mapping is omitted, legacy Processor handling remains in effect.
- Required input fields come dynamically from the `tbl_input` schema:
  - DB `NOT NULL` columns are required.
  - `ID`, `Process`, and `Input_Identifier` are excluded from source requirements.
- `ID` is not required because it is auto-generated.
- `Process` is always read from `process_config.Process_ID`, not from the source DataFrame.
- `Input_Identifier` is generated by runtime, not required from Excel.
- Generate `Input_Identifier` per row as:

```text
<process_config.Process_ID>_<Case_ID>
```

- Insert optional columns only when the DataFrame header exactly matches a `tbl_input` DB column.
- Preserve extra non-DB DataFrame columns inside `Case_Json` when that DB column exists.
- Ignore a source `Process` column if present.
- If required fields are missing from the DataFrame, raise an exception and stop before inserting any rows.

## Insert Behavior

- Insert into `tbl_input` row by row.
- Commit each row independently.
- Let the DB reject duplicates, especially duplicate `Input_Identifier`; do not pre-deduplicate in Python.
- Treat a database-rejected duplicate `Input_Identifier` as an expected idempotent skip:
  - Roll back that row.
  - Increment `skipped_count` and record the Excel row number in `skipped_rows`.
  - Log the skip at `INFO` without a traceback; keep row details at `DEBUG`.
  - Do not increment `failed_count` or add the duplicate to `failed_rows`.
- If a row fails:
  - Roll back that row.
  - Record DataFrame/Excel row number and error in the insert summary.
  - Continue with the next row.
  - Keep earlier committed rows.
- If a row is missing a required value, skip that row and record the reason.
- Log JSON construction and successful mandatory-column validation at `INFO`; log row count and mandatory field names at `DEBUG`. Row validation failures use `WARNING`, with row number and reason at `DEBUG`. These preparation logs do not include input values or JSON payloads.
- Processor mapping logs total, mapped, and rejected row counts at `INFO`. Successful mappings log row number and numeric processor ID at `DEBUG`; mapping rejections log row number and reason at `WARNING`, including the unmatched Processor value when present. These logs omit other input fields and JSON payloads. Mapping counts describe preparation, not successful database inserts. An absent mapping is logged at `DEBUG`.
- Newly inserted inputs initially retain an empty/null `Status` and are then included in queue creation.

## Queue Creation Behavior

- Select every `tbl_input` row whose `Process` matches `process_config.Process_ID` and whose `Status` is null, empty, or whitespace.
- For each eligible input, insert one `tbl_queue` row per distinct process application:
  - `Case_Details` is the input ID.
  - `Application_Details` is the KeyStep application ID.
  - `Processing_Status` is `queue_config.eligible_status`, defaulting to `Queue Created`.
- After the complete queue set succeeds, update the input to the same status and set `QueueCreation_timestamp = CURRENT_TIMESTAMP`.
- Commit the complete queue set and input update as one transaction per input.
- If any queue insert or the input update fails, roll back that input's complete queue set, leave it eligible for retry, record the failure, and continue with later inputs.
- Store aggregate results in `runtime_config.queue_creation_summary`.

## Error Behavior

- Missing `QueueFileLocation`, missing Excel file, unsupported source, unconfigured API source, missing required source fields, missing/invalid process KeySteps, nonexistent application IDs, missing `state["queue_db"]`, or missing `process_config.Process_ID` should set runtime failure state and prevent moving to `get_transaction`.
- Row-level missing values should be recorded as failures without stopping later rows. Duplicate identifiers should be recorded separately as informational skips.
- The graph should route to `end` or stop cleanly after failure instead of continuing transaction fetch.

## Test Plan

- `masterbot: false` skips Excel loading.
- `masterbot: true` + `Queue: Excel` reads the Excel file.
- `masterbot: true` + `Queue: API` uses the API adapter and reports a clear configuration error until API details are implemented.
- Blank/zero interval permits exactly one successful master-queue run per framework execution.
- Positive interval becomes due only after the configured elapsed time.
- Periodic waiting rejects zero, negative, blank, or nonnumeric `wait_seconds`.
- Missing required `Case_ID` field fails before inserts.
- Missing required cell values skip only those rows.
- Valid rows insert into `tbl_input`.
- `tbl_input.Process` is set from `process_config.Process_ID`.
- Source `Process` column is ignored.
- `Input_Identifier` is generated as `Process_ID_Case_ID`.
- Optional DB-matching columns are inserted.
- Extra non-DB columns are ignored.
- Duplicate `Input_Identifier` is rejected by the DB, recognized for both SQLite and MySQL, logged at `INFO`, counted as skipped rather than failed, and the load continues.
- Earlier rows remain committed after a later row fails.
- Later valid rows are still inserted after a failed row.
- Duplicate KeyStep applications create only one queue row per input.
- Distinct applications retain the order of their first sequenced KeyStep.
- Inputs for other processes or with populated statuses are ignored.
- Each successfully queued input receives the configured status and queue creation timestamp.
- A queue failure rolls back the complete queue set for that input and does not prevent later inputs from being queued.
- Rerunning master queue creation does not duplicate queues for inputs already marked queue-created.
