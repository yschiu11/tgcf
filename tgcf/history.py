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

    def set_sent_id(self, src_chat: int, src_msg: int, dest_chat: int, dest_msg: int) -> None:
        """Persist the destination message ID for one source-destination pair."""

    def get_dest_map(self, src_chat: int, src_msg: int) -> dict[int, int | None]:
        """Return destination mapping for one source message."""

    def prune(self, older_than_ts: int) -> None:
        """Delete stale rows older than `older_than_ts`."""


class NoopHistoryStore:
    """No-op store for flows that do not need history persistence/reuse."""

    def add_placeholder(self, src_chat: int, src_msg: int, dest_chats: list[int]) -> None:
        return

    def set_sent_id(self, src_chat: int, src_msg: int, dest_chat: int, dest_msg: int) -> None:
        return

    def get_dest_map(self, src_chat: int, src_msg: int) -> dict[int, int | None]:
        return {}

    def prune(self, older_than_ts: int) -> None:
        return


class SQLiteHistoryStore:
    """SQLite-backed history store for durable edit/delete synchronization."""

    def __init__(self, db_path: str | Path, prune_batch_size: int = 1000) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.prune_batch_size = max(1, prune_batch_size)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            with self.conn:
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.execute("PRAGMA synchronous=NORMAL")
                self.conn.execute("PRAGMA busy_timeout=3000")
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

    def prune(self, older_than_ts: int) -> None:
        pass

    def close(self) -> None:
        with self._lock:
            self.conn.close()
