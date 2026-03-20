"""Durable message history store for edit/delete sync."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Protocol


class HistoryStore(Protocol):
    """Storage contract for source -> destination message mappings."""

    def add_placeholder(self, src_chat: int, src_msg: int, dest_chats: list[int]) -> None:
        """Reserve mapping rows before destination message IDs are known."""


    def set_sent_ids(self, rows: list[tuple[int, int, int, int]]) -> None:
        """Persist multiple source-destination message mappings in bulk."""

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

    def set_sent_ids(self, rows: list[tuple[int, int, int, int]]) -> None:
        for src_chat, src_msg, dest_chat, dest_msg in rows:
            self.set_sent_id(src_chat, src_msg, dest_chat, dest_msg)

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
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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

    def set_sent_ids(self, rows: list[tuple[int, int, int, int]]) -> None:
        if not rows:
            return
        now = int(time.time())
        db_rows = [(s_chat, s_msg, d_chat, d_msg, now, now) for s_chat, s_msg, d_chat, d_msg in rows]
        with self._lock:
            with self.conn:
                self.conn.executemany(
                    """
                    INSERT INTO history (src_chat, src_msg, dest_chat, dest_msg, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (src_chat, src_msg, dest_chat)
                    DO UPDATE SET dest_msg=excluded.dest_msg, updated_at=excluded.updated_at
                    """,
                    db_rows,
                )

    def get_dest_map(self, src_chat: int, src_msg: int) -> dict[int, int | None]:
        with self._lock:
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
        with self._lock:
            if limit <= 0:
                with self.conn:
                    self.conn.execute("DELETE FROM history")
                return

            row = self.conn.execute("SELECT COUNT(*) FROM history").fetchone()
            if row is None:
                return
            to_remove = row[0] - limit
            if to_remove <= 0:
                return

            with self.conn:
                self.conn.execute(
                    """
                    DELETE FROM history WHERE rowid IN (
                        SELECT rowid FROM history
                        ORDER BY created_at ASC
                        LIMIT ?
                    )
                    """,
                    (to_remove,),
                )

    def close(self) -> None:
        with self._lock:
            self.conn.close()
