"""Durable message history store for edit/delete sync."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Protocol


class HistoryStore(Protocol):
    """Storage contract for source -> destination message mappings."""

    def add_placeholder(self, src_chat: int, src_msg: int, dest_chats: list[int]) -> None:
        """Reserve mapping rows before destination message IDs are known."""

    def set_sent_id(self, src_chat: int, src_msg: int, dest_chat: int, dest_msg: int) -> None:
        """Persist the destination message ID for one source-destination pair."""

    def get_dest_map(self, src_chat: int, src_msg: int) -> dict[int, int | None]:
        """Return destination mapping for one source message."""

    def prune(self, limit: int) -> None:
        """Keep at most ``limit`` source-message mapping groups."""


class MemoryHistoryStore:
    """In-memory store for one-off flows that do not require durability."""

    def __init__(self) -> None:
        self._records: dict[tuple[int, int], dict[int, int | None]] = {}

    def add_placeholder(self, src_chat: int, src_msg: int, dest_chats: list[int]) -> None:
        src_uid = (src_chat, src_msg)
        if src_uid not in self._records:
            self._records[src_uid] = {}

        for dest_chat in dest_chats:
            self._records[src_uid][dest_chat] = None

    def set_sent_id(self, src_chat: int, src_msg: int, dest_chat: int, dest_msg: int) -> None:
        src_uid = (src_chat, src_msg)
        if src_uid not in self._records:
            self._records[src_uid] = {}
        self._records[src_uid][dest_chat] = dest_msg

    def get_dest_map(self, src_chat: int, src_msg: int) -> dict[int, int | None]:
        src_uid = (src_chat, src_msg)
        return dict(self._records.get(src_uid, {}))

    def prune(self, limit: int) -> None:
        while len(self._records) > limit:
            self._records.pop(next(iter(self._records)))


class SQLiteHistoryStore:
    """SQLite-backed history store for durable edit/delete synchronization."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    src_chat INTEGER NOT NULL,
                    src_msg INTEGER NOT NULL,
                    dest_chat INTEGER NOT NULL,
                    dest_msg INTEGER NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (src_chat, src_msg, dest_chat)
                )
                """
            )
            self.conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_created
                ON history(created_at)
                """
            )

    def add_placeholder(self, src_chat: int, src_msg: int, dest_chats: list[int]) -> None:
        if not dest_chats:
            return

        now = int(time.time())
        rows = [(src_chat, src_msg, dest_chat, now, now) for dest_chat in dest_chats]
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO history (src_chat, src_msg, dest_chat, dest_msg, created_at, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?)
                ON CONFLICT (src_chat, src_msg, dest_chat)
                DO UPDATE SET updated_at=excluded.updated_at
                """,
                rows,
            )

    def set_sent_id(self, src_chat: int, src_msg: int, dest_chat: int, dest_msg: int) -> None:
        now = int(time.time())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO history (src_chat, src_msg, dest_chat, dest_msg, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (src_chat, src_msg, dest_chat)
                DO UPDATE SET dest_msg=excluded.dest_msg, updated_at=excluded.updated_at
                """,
                (src_chat, src_msg, dest_chat, dest_msg, now, now),
            )

    def get_dest_map(self, src_chat: int, src_msg: int) -> dict[int, int | None]:
        rows = self.conn.execute(
            """
            SELECT dest_chat, dest_msg
            FROM history
            WHERE src_chat=? AND src_msg=?
            """,
            (src_chat, src_msg),
        ).fetchall()
        return {int(dest_chat): (int(dest_msg) if dest_msg is not None else None) for dest_chat, dest_msg in rows}

    def prune(self, limit: int) -> None:
        if limit <= 0:
            with self.conn:
                self.conn.execute("DELETE FROM history")
            return

        total = self.conn.execute(
            """
            SELECT COUNT(*)
            FROM (SELECT 1 FROM history GROUP BY src_chat, src_msg)
            """
        ).fetchone()[0]

        to_remove = total - limit
        if to_remove <= 0:
            return

        with self.conn:
            self.conn.execute(
                """
                DELETE FROM history
                WHERE (src_chat, src_msg) IN (
                    SELECT src_chat, src_msg
                    FROM history
                    GROUP BY src_chat, src_msg
                    ORDER BY MIN(created_at) ASC, src_chat ASC, src_msg ASC
                    LIMIT ?
                )
                """,
                (to_remove,),
            )

    def close(self) -> None:
        self.conn.close()
