"""Durable message history store for edit/delete sync."""

from __future__ import annotations

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
