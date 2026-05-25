from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class QueueDatabaseError(RuntimeError):
    pass


class QueueDatabaseAdapter(Protocol):
    config: dict[str, Any]
    db_type: str
    placeholder: str
    queries: dict[str, str]

    def connect(self) -> Any:
        ...

    def close(self) -> None:
        ...

    def describe(self) -> dict[str, Any]:
        ...


@dataclass
class SQLiteQueueDatabase:
    path: Path
    config: dict[str, Any]
    queries: dict[str, str]
    db_type: str = "sqlite"
    placeholder: str = "?"
    connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if not self.path.exists():
            raise QueueDatabaseError(f"SQLite queue database file not found: {self.path}")
        if not self.path.is_file():
            raise QueueDatabaseError(f"SQLite queue database path is not a file: {self.path}")

        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        return self.connection

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def describe(self) -> dict[str, Any]:
        return {"type": "sqlite", "sqlite_path": str(self.path)}


@dataclass
class MySQLQueueDatabase:
    config: dict[str, Any]
    queries: dict[str, str]
    db_type: str = "mysql"
    placeholder: str = "%s"
    connection: Any = None

    def connect(self) -> Any:
        import mysql.connector

        self.connection = mysql.connector.connect(
            host=_required(self.config, "host"),
            port=int(_required(self.config, "port")),
            database=_required(self.config, "database"),
            user=_required(self.config, "username"),
            password=_required(self.config, "password"),
            charset=self.config.get("charset") or "utf8mb4",
            connection_timeout=int(self.config.get("connect_timeout") or 10),
        )
        return self.connection

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def describe(self) -> dict[str, Any]:
        return {
            "type": "mysql",
            "host": self.config.get("host"),
            "port": self.config.get("port"),
            "database": self.config.get("database"),
            "charset": self.config.get("charset") or "utf8mb4",
            "connect_timeout": self.config.get("connect_timeout") or 10,
        }


def initialize_queue_db_adapter(state: dict[str, Any]) -> QueueDatabaseAdapter:
    config = dict(state.get("config", {}).get("queue_database", {}))
    db_type = str(config.get("type") or "").strip().lower()
    if not db_type:
        raise QueueDatabaseError("queue_database.type is required")

    if db_type == "sqlite":
        adapter = SQLiteQueueDatabase(
            path=_resolve_sqlite_path(config, state.get("config_context", {})),
            config=config,
            queries=load_queue_queries("sqlite", state.get("config_context", {})),
        )
    elif db_type == "mysql":
        adapter = MySQLQueueDatabase(
            config=config,
            queries=load_queue_queries("mysql", state.get("config_context", {})),
        )
    else:
        raise QueueDatabaseError(f"Unsupported queue_database.type: {db_type}")

    adapter.connect()
    return adapter


def load_queue_queries(db_type: str, context: dict[str, str]) -> dict[str, str]:
    path = _queue_query_path(db_type, context)
    if not path.exists():
        raise QueueDatabaseError(f"Queue query file not found: {path}")
    return parse_named_sql(path.read_text(encoding="utf-8"), path)


def parse_named_sql(sql_text: str, source: Path | str = "<sql>") -> dict[str, str]:
    queries: dict[str, list[str]] = {}
    current_name: str | None = None

    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("-- name:"):
            current_name = stripped.split(":", 1)[1].strip()
            if not current_name:
                raise QueueDatabaseError(f"Empty query name in {source}")
            if current_name in queries:
                raise QueueDatabaseError(f"Duplicate query name '{current_name}' in {source}")
            queries[current_name] = []
            continue

        if current_name is not None:
            queries[current_name].append(line)

    parsed = {name: "\n".join(lines).strip() for name, lines in queries.items()}
    empty = [name for name, query in parsed.items() if not query]
    if empty:
        raise QueueDatabaseError(f"Empty SQL query block(s) in {source}: {', '.join(empty)}")
    return parsed


def _queue_query_path(db_type: str, context: dict[str, str]) -> Path:
    share_root = context.get("share_root")
    if not share_root:
        raise QueueDatabaseError("config_context.share_root is required to load queue queries")

    if db_type == "sqlite":
        filename = "sqlite_queue_queries.sql"
    elif db_type == "mysql":
        filename = "mysql_queue_queries.sql"
    else:
        raise QueueDatabaseError(f"Unsupported queue query db type: {db_type}")

    return Path(share_root) / "common" / "sql" / filename


def _resolve_sqlite_path(config: dict[str, Any], context: dict[str, str]) -> Path:
    raw_path = str(config.get("sqlite_path") or "").strip()
    if not raw_path:
        raise QueueDatabaseError("queue_database.sqlite_path is required for sqlite")

    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    project_config_dir = Path(context["project_config_dir"])
    project_candidate = (project_config_dir / candidate).resolve()
    if project_candidate.exists():
        return project_candidate

    share_config_candidate = (Path(context["share_root"]) / "config" / candidate).resolve()
    if share_config_candidate.exists():
        return share_config_candidate

    return project_candidate


def _required(config: dict[str, Any], key: str) -> Any:
    value = config.get(key)
    if value is None or value == "":
        raise QueueDatabaseError(f"queue_database.{key} is required for mysql")
    return value
