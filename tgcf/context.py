import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from telethon import TelegramClient

from tgcf.config import Config, Forward, write_config
from tgcf.history import HistoryStore, SQLiteHistoryStore
from tgcf.pipeline import ForwardingPipeline


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
    # Map src_chat -> (Forward object, resolved dest_chats)
    routing_map: dict[int, tuple[Forward, list[int]]] = field(default_factory=dict)
    admins: list[int] = field(default_factory=list)

    history: HistoryStore | None = None
    pipeline: 'ForwardingPipeline' = None

    # Album buffering
    flush_tasks: dict[int, asyncio.Task] = field(default_factory=dict)

    def __post_init__(self):
        if self.history is None:
            config_dir = Path(self.config_path).expanduser().parent
            self.history = SQLiteHistoryStore(config_dir / "tgcf.history.sqlite3")

    def bind_client(self, client: TelegramClient):
        self.client = client
        self.pipeline = ForwardingPipeline(self.client, self.config, self.history)

    def save_config(self) -> None:
        """Save the config to the config file."""
        write_config(self.config, self.config_path)
