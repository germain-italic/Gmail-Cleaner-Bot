"""Database models and operations using SQLite."""

import sqlite3
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from contextlib import contextmanager

from .config import DATABASE_PATH


class RuleAction(Enum):
    DELETE = "delete"
    ARCHIVE = "archive"
    MARK_READ = "mark_read"
    LABEL = "label"


class RuleField(Enum):
    SUBJECT = "subject"
    FROM = "from"
    TO = "to"
    BODY = "body"


class RuleOperator(Enum):
    CONTAINS = "contains"
    CONTAINS_EXACT = "contains_exact"
    EQUALS = "equals"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    REGEX = "regex"


@dataclass
class Rule:
    id: Optional[int]
    name: str
    field: RuleField
    operator: RuleOperator
    value: str
    action: RuleAction
    action_param: Optional[str]  # e.g., label name for LABEL action
    older_than_days: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: tuple) -> "Rule":
        return cls(
            id=row[0],
            name=row[1],
            field=RuleField(row[2]),
            operator=RuleOperator(row[3]),
            value=row[4],
            action=RuleAction(row[5]),
            action_param=row[6],
            older_than_days=row[7],
            enabled=bool(row[8]),
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
        )


@dataclass
class LogEntry:
    id: Optional[int]
    rule_id: int
    rule_name: str
    message_id: str
    message_subject: str
    message_from: str
    action: RuleAction
    success: bool
    error_message: Optional[str]
    executed_at: datetime

    @classmethod
    def from_row(cls, row: tuple) -> "LogEntry":
        return cls(
            id=row[0],
            rule_id=row[1],
            rule_name=row[2],
            message_id=row[3],
            message_subject=row[4],
            message_from=row[5],
            action=RuleAction(row[6]),
            success=bool(row[7]),
            error_message=row[8],
            executed_at=datetime.fromisoformat(row[9]),
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    field TEXT NOT NULL,
    operator TEXT NOT NULL,
    value TEXT NOT NULL,
    action TEXT NOT NULL,
    action_param TEXT,
    older_than_days INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    rule_name TEXT NOT NULL,
    message_id TEXT NOT NULL,
    message_subject TEXT,
    message_from TEXT,
    action TEXT NOT NULL,
    success INTEGER NOT NULL,
    error_message TEXT,
    executed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_executed_at ON logs(executed_at);
CREATE INDEX IF NOT EXISTS idx_logs_rule_id ON logs(rule_id);
"""


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Rule operations
    def create_rule(self, rule: Rule) -> int:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO rules (name, field, operator, value, action, action_param,
                                   older_than_days, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.name,
                    rule.field.value,
                    rule.operator.value,
                    rule.value,
                    rule.action.value,
                    rule.action_param,
                    rule.older_than_days,
                    int(rule.enabled),
                    now,
                    now,
                ),
            )
            return cursor.lastrowid

    def get_rules(self, enabled_only: bool = False) -> list[Rule]:
        query = "SELECT * FROM rules"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"

        with self._connect() as conn:
            cursor = conn.execute(query)
            return [Rule.from_row(row) for row in cursor.fetchall()]

    def get_rule(self, rule_id: int) -> Optional[Rule]:
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,))
            row = cursor.fetchone()
            return Rule.from_row(row) if row else None

    def update_rule(self, rule: Rule) -> bool:
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE rules SET name=?, field=?, operator=?, value=?, action=?,
                                 action_param=?, older_than_days=?, enabled=?, updated_at=?
                WHERE id = ?
                """,
                (
                    rule.name,
                    rule.field.value,
                    rule.operator.value,
                    rule.value,
                    rule.action.value,
                    rule.action_param,
                    rule.older_than_days,
                    int(rule.enabled),
                    now,
                    rule.id,
                ),
            )
            return cursor.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
            return cursor.rowcount > 0

    def toggle_rule(self, rule_id: int) -> bool:
        with self._connect() as conn:
            conn.execute(
                "UPDATE rules SET enabled = NOT enabled, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), rule_id),
            )
            return True

    # Log operations
    def add_log(self, entry: LogEntry) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO logs (rule_id, rule_name, message_id, message_subject,
                                  message_from, action, success, error_message, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.rule_id,
                    entry.rule_name,
                    entry.message_id,
                    entry.message_subject,
                    entry.message_from,
                    entry.action.value,
                    int(entry.success),
                    entry.error_message,
                    entry.executed_at.isoformat(),
                ),
            )
            return cursor.lastrowid

    def get_logs(
        self,
        limit: int = 100,
        rule_id: Optional[int] = None,
        success_only: Optional[bool] = None
    ) -> list[LogEntry]:
        query = "SELECT * FROM logs WHERE 1=1"
        params = []

        if rule_id is not None:
            query += " AND rule_id = ?"
            params.append(rule_id)

        if success_only is not None:
            query += " AND success = ?"
            params.append(int(success_only))

        query += " ORDER BY executed_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [LogEntry.from_row(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total_rules = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
            active_rules = conn.execute(
                "SELECT COUNT(*) FROM rules WHERE enabled = 1"
            ).fetchone()[0]
            total_actions = conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
            successful = conn.execute(
                "SELECT COUNT(*) FROM logs WHERE success = 1"
            ).fetchone()[0]

            return {
                "total_rules": total_rules,
                "active_rules": active_rules,
                "total_actions": total_actions,
                "successful_actions": successful,
                "failed_actions": total_actions - successful,
            }

    def clear_old_logs(self, days: int = 30) -> int:
        cutoff = datetime.now().isoformat()[:10]  # Simple date comparison
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM logs WHERE date(executed_at) < date(?, ?)",
                (cutoff, f"-{days} days"),
            )
            return cursor.rowcount
