from __future__ import annotations

from typing import Any, Protocol

from framework.logging_config import get_logger


class DatabaseConnectionError(RuntimeError):
    pass


class DatabaseConnectionProvider(Protocol):
    db_type: str
    connection: Any

    def connect(self) -> Any:
        ...


def ensure_database_connection(db: DatabaseConnectionProvider) -> None:
    """Validate before SQL; reconnect MySQL only outside an active transaction.

    Project database adapters can use this same guard before creating cursors.
    Queries and commits must never be replayed automatically after a disconnect.
    """
    if db.db_type not in {"mysql", "sqlite"}:
        raise DatabaseConnectionError(f"Unsupported database type: {db.db_type}")
    logger = get_logger("runtime.database")
    if db.connection is None:
        try:
            db.connect()
        except Exception:
            logger.error("Database connection establishment failed: db_type=%s", db.db_type)
            raise
        if db.connection is not None:
            logger.info("Database connection established: db_type=%s", db.db_type)
    connection = db.connection
    if connection is None:
        logger.error("Database adapter did not establish a connection: db_type=%s", db.db_type)
        raise DatabaseConnectionError("Database adapter did not establish a connection")

    if db.db_type == "mysql":
        from mysql.connector.errors import Error

        # Read the driver's cached transaction status before ping can change it.
        if connection.in_transaction:
            try:
                connection.ping(reconnect=False)
            except Error as error:
                logger.error(
                    "Database validation failed during an active transaction; "
                    "automatic reconnection blocked: db_type=mysql"
                )
                raise DatabaseConnectionError(
                    "Database connection validation failed during an active transaction; "
                    "automatic reconnection is disabled to protect pending changes"
                ) from error
        else:
            try:
                connection.ping(reconnect=False)
            except Error:
                logger.warning(
                    "Database connection unavailable; attempting reconnection: "
                    "db_type=mysql, attempts=3, delay_seconds=2"
                )
                try:
                    connection.ping(reconnect=True, attempts=3, delay=2)
                except Error:
                    logger.error("Database reconnection failed: db_type=mysql")
                    raise
                logger.info("Database connection recovered: db_type=mysql")
    else:
        # SQLite has no server-side idle timeout. A closed handle fails here;
        # reopening it could conceal a lost transaction.
        try:
            cursor = connection.execute("SELECT 1")
        except Exception:
            logger.error("Database connection validation failed: db_type=sqlite")
            raise
        cursor.close()
    logger.debug("Database connection validated: db_type=%s", db.db_type)
