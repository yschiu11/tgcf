import asyncio
from dataclasses import dataclass, field

from telethon import TelegramClient
from tgcf.config import Config, write_config

from tgcf.utils import AlbumBuffer


@dataclass
class TgcfContext:
    """Runtime state for a tgcf instance."""
    # Immutable config loaded once at startup
    config: Config
    config_path: str

    # Client connection, set after login
    client: TelegramClient | None = None
    is_bot: bool | None = None

    # Resolved mappings, compute once after client connects
    from_to: dict[int, list[int]] = field(default_factory=dict)
    admins: list[int] = field(default_factory=list)

    # Message tracking, edit, delete, reply sync
    stored: dict[tuple[int, int], dict[int, int]] = field(default_factory=dict)

    # Album buffering
    album_buffers: dict[int, AlbumBuffer] = field(default_factory=dict)
    flush_tasks: dict[int, asyncio.Task] = field(default_factory=dict)

    def prune_stored(self, keep_last: int) -> None:
        """
        Remove old entries from stored, keeping only the last `keep_last` entries.
        """

        while len(self.stored) > keep_last:
            self.stored.pop(next(iter(self.stored)))

    def save_config(self) -> None:
        """Save the config to the config file."""
        write_config(self.config, self.config_path)
