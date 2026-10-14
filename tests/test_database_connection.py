from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mysql.connector.errors import InterfaceError

from framework.cli import main
from framework.results import Outcome
from framework.runtime.database_connection import (
    DatabaseConnectionError,
    ensure_database_connection,
)
from framework.runtime.queue_db import SQLiteQueueDatabase


class DatabaseConnectionTests(unittest.TestCase):
    def test_missing_handle_is_connected_and_validated(self):
        db = Mock(db_type="mysql", connection=None)
        connection = Mock(in_transaction=False)
        db.connect.side_effect = lambda: setattr(db, "connection", connection)
        ensure_database_connection(db)
        db.connect.assert_called_once_with()
        connection.ping.assert_called_once_with(reconnect=False)

    def test_recovery_logs_attempt_and_success_without_sensitive_values(self):
        connection = Mock(in_transaction=False)
        connection.ping.side_effect = [InterfaceError("secret-password customer-payload"), None]
        db = Mock(db_type="mysql", connection=connection)
        with self.assertLogs("framework.runtime.database", level="DEBUG") as captured:
            ensure_database_connection(db)
        output = "\n".join(captured.output)
        self.assertIn("attempting reconnection", output)
        self.assertIn("Database connection recovered", output)
        self.assertNotIn("secret-password", output)
        self.assertNotIn("customer-payload", output)

    def test_failed_recovery_is_logged_without_false_success(self):
        connection = Mock(in_transaction=False)
        connection.ping.side_effect = InterfaceError("secret-password")
        with self.assertLogs("framework.runtime.database", level="DEBUG") as captured:
            with self.assertRaises(InterfaceError):
                ensure_database_connection(Mock(db_type="mysql", connection=connection))
        output = "\n".join(captured.output)
        self.assertIn("Database reconnection failed", output)
        self.assertNotIn("Database connection recovered", output)
        self.assertNotIn("secret-password", output)

    def test_adapter_that_does_not_connect_fails_explicitly(self):
        db = Mock(db_type="mysql", connection=None)
        with self.assertRaisesRegex(DatabaseConnectionError, "did not establish"):
            ensure_database_connection(db)

    def test_sqlite_validation_preserves_pending_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite"
            sqlite3.connect(path).close()
            db = SQLiteQueueDatabase(path=path, config={}, queries={})
            ensure_database_connection(db)
            try:
                connection = db.connection
                connection.execute("CREATE TABLE example (id INTEGER)")
                connection.execute("INSERT INTO example VALUES (1)")
                ensure_database_connection(db)
                self.assertIs(connection, db.connection)
                self.assertTrue(connection.in_transaction)
                connection.rollback()
                self.assertEqual([], connection.execute("SELECT * FROM example").fetchall())
                connection.close()
                with self.assertRaises(sqlite3.ProgrammingError):
                    ensure_database_connection(db)
            finally:
                db.close()

    def test_cli_returns_failure_for_terminal_system_exception(self):
        for status, expected in (
            (Outcome.SYSTEM_EXCEPTION, 1),
            (Outcome.NO_TRANSACTION, 0),
            (Outcome.SUCCESS, 0),
        ):
            with self.subTest(status=status), patch("sys.argv", ["framework", "config.json"]), patch(
                "framework.cli.run_graph", return_value={"runtime_config": {"last_status": status}}
            ):
                self.assertEqual(expected, main())


if __name__ == "__main__":
    unittest.main()
