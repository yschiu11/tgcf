import asyncio
from dataclasses import dataclass, field

from telethon import TelegramClient
from tgcf.config import Config
from tgcf.storage import EventUid
from tgcf.utils import AlbumBuffer


@dataclass
class TgcfContext:
    """Runtime state for a tgcf instance."""
    # Immutable config loaded once at startup
    config: Config

    # Client connection, set after login
    client: TelegramClient | None = None
    is_bot: bool | None = None

    # Resolved mappings, compute once after client connects
    from_to: dict[int, list[int]] = field(default_factory=dict)
    admins: list[int] = field(default_factory=list)

    # Message tracking, edit, delete, reply sync
    stored: dict[EventUid, dict[int, int]] = field(default_factory=dict)

    # Album buffering
    album_buffers: dict[int, AlbumBuffer] = field(default_factory=dict)
    flush_tasks: dict[int, asyncio.Task] = field(default_factory=dict)

    def prune_stored(self, keep_last: int) -> None:
        """
        Remove old entries from stored, keeping only the last `keep_last` entries.
        """

        excess = len(self.stored) - keep_last
        if excess > 0:
            for key in list(self.stored.keys())[:excess]:
                del self.stored[key]
