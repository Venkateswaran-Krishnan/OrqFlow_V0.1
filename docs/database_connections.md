# Database connection recovery

All framework database queries pass through `execute_queue_query()`, which calls
`ensure_database_connection()` before creating a cursor. Startup uses the same
validation. This covers master input inserts, queue creation, transaction fetching,
eligibility checks, schema reads, and final status updates.

MySQL connections are checked using `ping(reconnect=False)`. If validation fails
and the driver's cached `in_transaction` flag was false before the check, the
guard calls `ping(reconnect=True, attempts=3, delay=2)`. A stale connection can
therefore recover after a long API call, browser operation, or scheduler wait.
During an active transaction, validation uses `ping(reconnect=False)` and fails
if the connection is lost. Reconnecting at that point would lose the pending
transaction. Queries and commits are never automatically retried: a disconnect
can leave the result of a write unknown.

Completed eligibility reads and empty transaction fetches commit their read
transactions before the scheduler can wait. Input selection also ends its read
transaction after materializing the rows. Related queue writes remain together
until their existing commit or rollback.

SQLite validates its handle with `SELECT 1`. It has no server idle timeout; a
closed handle fails rather than silently concealing a lost transaction. Adapters
with a missing handle are connected before validation.

Project hooks that create their own database connections must use the shared
guard too. Their adapter needs `db_type` (`mysql` or `sqlite`), `connection`, and
`connect()`:

```python
from framework.runtime.database_connection import ensure_database_connection

ensure_database_connection(project_db)
cursor = project_db.connection.cursor()
try:
    cursor.execute(sql, parameters)
    project_db.connection.commit()
finally:
    cursor.close()
```

Call the guard before each SQL operation. Keep transactions short and complete
them before long external work. Do not reconnect or retry a commit on failure;
let the operation fail and reconcile the write result before retrying.

The CLI returns exit code 1 when the final runtime status is `SYSTEM_EXCEPTION`,
including master queue creation failures. Install the updated framework package
in automation environments to apply these changes; existing installed wheels
are unaffected by changes to this source checkout.

## Operational logs

The `framework.runtime.database` logger uses the configured framework handlers:

| Level | Event |
| --- | --- |
| DEBUG | Connection validation completed; backend type only. |
| INFO | A missing connection was established, or MySQL reconnection succeeded. |
| WARNING | MySQL validation failed outside a transaction; three reconnect attempts with a two-second delay are about to begin. |
| ERROR | Connection establishment, reconnection, or SQLite validation failed; or MySQL validation failed inside an active transaction and reconnection was blocked. |

These events omit connection configuration, credentials, SQL, parameters,
customer payloads, and raw exception text. Calling runtime nodes retain their
existing exception handling and failure logging. Routine healthy checks use
DEBUG to avoid adding per-query INFO noise on a busy database.

## Validation and deployment status (2026-10-13)

The source suite and connection logging tests run with
`.venv/Scripts/python.exe -m unittest discover -s tests -q`. Current results are
saved in `logs/database-connection-validation.log` and `logs/source-validation.log`.
MySQL recovery tests simulate driver disconnects; SQLite tests use a local
database. Live MySQL recovery remains unverified.

Release `0.1.15` includes connection recovery, runtime logging, and terminal CLI
failure exit codes. The wheel is `dist/framework-0.1.15-py3-none-any.whl`;
build and release validation output are saved in `logs/wheel-build-0.1.15.log`
and `logs/release-validation-0.1.15.log`. Existing `0.1.14` wheels predate these
changes. No installation or deployment has been performed for this release.
