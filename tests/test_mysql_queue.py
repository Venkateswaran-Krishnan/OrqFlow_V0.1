from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import pandas as pd
from mysql.connector import MySQLConnection
from mysql.connector.cursor import MySQLCursorBufferedDict
from mysql.connector.errors import IntegrityError

from framework.runtime.queue_db import (
    MySQLQueueDatabase,
    execute_queue_query,
    load_queue_queries,
)
from framework.runtime.queue_runtime import DatabaseQueue, create_master_queue


class MySQLQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = Mock(spec_set=MySQLConnection)
        self.db = MySQLQueueDatabase(
            config={},
            queries=load_queue_queries(
                "mysql", {"share_root": str(Path(__file__).resolve().parents[1] / "share")}
            ),
            connection=self.connection,
        )
        self.state = {
            "queue_db": self.db,
            "config": {
                "process_config": {
                    "Process_ID": "100",
                    "settings": {"masterbot": True, "bot": "BOT-1"},
                }
            },
            "runtime_config": {"active_application_id": 68},
            "key_steps": pd.DataFrame([
                {"State": "PROCESS_TRANSACTION", "Sequence": 1, "Application": 68}
            ]),
        }

    def cursor(self, rows=(), *, lastrowid=None, rowcount=1, error=None):
        cursor = Mock(spec_set=MySQLCursorBufferedDict)
        cursor.fetchall.return_value = list(rows)
        cursor.fetchone.return_value = rows[0] if rows else None
        cursor.lastrowid = lastrowid
        cursor.rowcount = rowcount
        cursor.execute.side_effect = error
        return cursor

    def use_cursors(self, *cursors):
        self.connection.cursor.side_effect = cursors
        self.addCleanup(self.assert_cursors_closed, cursors)

    def assert_cursors_closed(self, cursors):
        self.assertEqual(
            [call(dictionary=True, buffered=True)] * len(cursors),
            self.connection.cursor.call_args_list,
        )
        for cursor in cursors:
            cursor.close.assert_called_once_with()

    def master_cursors(self, *, insert_error=None, updated_count=1):
        schema = [
            {"Field": name, "Null": "NO", "Key": "PRI" if name == "ID" else ""}
            for name in ("ID", "Process", "Case_ID", "Input_Identifier")
        ]
        return (
            self.cursor([{"ID": 68}]),
            self.cursor(schema),
            self.cursor(lastrowid=7, error=insert_error),
            self.cursor([{"ID": 7}]),
            self.cursor(lastrowid=9),
            self.cursor(rowcount=updated_count),
        )

    def run_master(self):
        with patch(
            "framework.runtime.queue_runtime._load_input_dataframe",
            return_value=pd.DataFrame([{"Case_ID": "CASE-1"}]),
        ):
            create_master_queue(self.state)
        self.assertNotIn("last_error", self.state["runtime_config"])
        return self.state["runtime_config"]

    def test_master_queue_uses_mysql_cursors_for_validation_insert_and_queue_creation(self):
        cursors = self.master_cursors()
        self.use_cursors(*cursors)

        runtime = self.run_master()

        self.assertEqual([7], runtime["input_load_summary"]["inserted_input_ids"])
        self.assertEqual(1, runtime["queue_creation_summary"]["created_queue_count"])
        cursors[0].execute.assert_called_once_with(self.db.queries["select_application_ids"], ())
        cursors[2].execute.assert_called_once_with(
            "INSERT INTO tbl_input (Case_ID, Process, Input_Identifier)\nVALUES (%s, %s, %s);",
            ["CASE-1", "100", "100_CASE-1"],
        )
        cursors[4].execute.assert_called_once_with(
            self.db.queries["insert_tbl_queue"], [7, 68, "Queue Created"]
        )
        cursors[5].execute.assert_called_once_with(
            self.db.queries["mark_input_queue_created"], ["Queue Created", 7, "100"]
        )
        self.assertEqual(2, self.connection.commit.call_count)

    def test_duplicate_input_rolls_back_and_continues_queue_creation(self):
        self.use_cursors(*self.master_cursors(
            insert_error=IntegrityError("Duplicate entry", errno=1062)
        ))

        runtime = self.run_master()

        self.assertEqual(1, runtime["input_load_summary"]["skipped_count"])
        self.assertEqual(1, runtime["queue_creation_summary"]["created_queue_count"])
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_called_once_with()

    def test_failed_input_update_rolls_back_queue_inserts(self):
        self.use_cursors(*self.master_cursors(updated_count=0))

        runtime = self.run_master()

        self.assertEqual(1, runtime["queue_creation_summary"]["failed_input_count"])
        self.assertEqual(0, runtime["queue_creation_summary"]["created_queue_count"])
        self.connection.rollback.assert_called_once_with()
        self.connection.commit.assert_called_once_with()

    def test_fetch_transaction_returns_named_columns_and_marks_in_progress(self):
        select = self.cursor([{
            "queue_id": 9, "input_id": 7, "queue_application_details": 68,
            "queue_processing_status": "Queue Created", "input_case_json": '{"case": "CASE-1"}',
        }])
        update = self.cursor()
        self.use_cursors(select, update)

        txn = DatabaseQueue(self.state).fetch_next()

        self.assertEqual(9, txn["queue_id"])
        self.assertEqual({"case": "CASE-1"}, txn["case_json"])
        self.assertEqual("In Processing", txn["queue_processing_status"])
        select.execute.assert_called_once_with(
            self.db.queries["fetch_next_transaction"],
            ["In Processing", "Queue Created", 68, "100", "In Processing"],
        )
        update.execute.assert_called_once_with(
            self.db.queries["mark_transaction_in_progress"], ["In Processing", "BOT-1", 9]
        )
        self.connection.commit.assert_called_once_with()

    def test_empty_transaction_and_configured_eligibility(self):
        eligible = self.cursor([{"ID": 9}])
        self.use_cursors(self.cursor(), eligible, self.cursor())
        queue = DatabaseQueue(self.state)

        self.assertIsNone(queue.fetch_next())
        self.assertTrue(queue.has_eligible_transactions())
        self.assertFalse(queue.has_eligible_transactions())
        eligible.execute.assert_called_once_with(
            self.db.queries["fetch_any_eligible_transaction"].format(application_placeholders="%s"),
            ["In Processing", "Queue Created", "100", 68],
        )
        self.connection.commit.assert_not_called()

    def test_all_final_statuses_bind_comment_and_cto_details(self):
        cursors = (self.cursor(), self.cursor(), self.cursor())
        self.use_cursors(*cursors)
        queue = DatabaseQueue(self.state)
        for cursor, (method, status, query) in zip(cursors, (
            (queue.mark_success, "Success", "mark_transaction_success"),
            (queue.mark_skipped, "Skipped", "mark_transaction_skipped"),
            (queue.mark_failed, "Failed", "mark_transaction_failed"),
        )):
            with self.subTest(status=status):
                txn = {"queue_id": 9}
                method(txn, "result", '{"code": 1}')
                cursor.execute.assert_called_once_with(
                    self.db.queries[query],
                    [status, "result", "result", "result", "result",
                     '{"code": 1}', '{"code": 1}', '{"code": 1}', 9],
                )
                self.assertEqual(status, txn["queue_processing_status"])
                self.assertEqual('{"code": 1}', txn["queue_cto_details"])
        self.assertEqual(3, self.connection.commit.call_count)

    def test_cursor_closes_when_execution_raises(self):
        error = RuntimeError("query failed")
        cursor = self.cursor(error=error)
        self.use_cursors(cursor)

        with self.assertRaisesRegex(RuntimeError, "query failed"):
            with execute_queue_query(self.db, "SELECT %s", [68]):
                self.fail("Execution failure must propagate")


if __name__ == "__main__":
    unittest.main()
