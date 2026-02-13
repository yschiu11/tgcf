"""Album buffering and grouped-message detection."""

from typing import TYPE_CHECKING

from telethon.client import TelegramClient
from telethon.hints import EntityLike

if TYPE_CHECKING:
    from tgcf.plugins import TgcfMessage

# Telegram albums can have up to 10 items. We search ±10 messages around
# the target to ensure we capture the full album even if there are gaps.
ALBUM_SEARCH_RADIUS = 10


class AlbumBuffer:
    """Manage buffering and detection of media albums (grouped messages)."""

    def __init__(self) -> None:
        self.messages: list["TgcfMessage"] = []
        self.current_group_id: int | None = None

    def add_message(self, tm: "TgcfMessage") -> None:
        """Add a message to the current album buffer."""
        self.messages.append(tm)
        self.current_group_id = tm.message.grouped_id

    def should_flush(self, next_grouped_id: int | None) -> bool:
        """Check whether the buffer should be flushed before the next message.

        Args:
            next_grouped_id: The grouped_id of the incoming message.

        Returns:
            True if the buffer has messages and the next message
            belongs to a different album.
        """
        if not self.messages:
            return False

        if self.current_group_id is None:
            return False

        return next_grouped_id != self.current_group_id

    def is_album(self) -> bool:
        """Check if buffer contains multiple messages."""
        return len(self.messages) > 1

    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self.messages) == 0

    def flush(self) -> list["TgcfMessage"]:
        """Return all buffered messages and reset the buffer."""
        if not self.messages:
            return []

        messages, self.messages = self.messages, []
        self.current_group_id = None
        return messages

    def clear(self) -> None:
        """Clear the buffer and release resources held by each message."""
        for tm in self.messages:
            tm.clear()
        self.messages.clear()
        self.current_group_id = None

    def get_messages(self) -> list["TgcfMessage"]:
        """Get all buffered messages."""
        return self.messages


async def fetch_album_by_message(
    client: TelegramClient,
    entity: EntityLike,
    msg_id: int,
    grouped_id: int,
) -> AlbumBuffer:
    """Fetch all messages in an album given one message from it.

    Searches ±ALBUM_SEARCH_RADIUS messages around ``msg_id`` and
    collects those sharing the same ``grouped_id``.

    Args:
        client: Authenticated Telegram client.
        entity: The chat/channel containing the album.
        msg_id: ID of any message in the album.
        grouped_id: The album's grouped_id.

    Returns:
        An AlbumBuffer containing the album's messages sorted by ID.
    """
    from tgcf.plugins import TgcfMessage

    album_buffer = AlbumBuffer()

    # Fetch nearby messages to find all album members
    messages = await client.get_messages(
        entity,
        ids=range(msg_id - ALBUM_SEARCH_RADIUS, msg_id + ALBUM_SEARCH_RADIUS + 1),
    )

    # Filter and wrap in TgcfMessage
    album_messages: list[TgcfMessage] = [
        TgcfMessage(m)
        for m in messages
        if m is not None and m.grouped_id == grouped_id
    ]

    # Sort by message ID to maintain order
    album_messages.sort(key=lambda m: m.message.id)
    for m in album_messages:
        album_buffer.add_message(m)

    return album_buffer
