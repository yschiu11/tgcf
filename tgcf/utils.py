"""Utility functions to smoothen your life."""

import logging
import os
import platform
import re
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from telethon.client import TelegramClient
from telethon.hints import EntityLike
from telethon.tl.custom.message import Message

from tgcf import __version__
from tgcf.config import CONFIG
from tgcf.plugin_models import STYLE_CODES

if TYPE_CHECKING:
    from tgcf.plugins import TgcfMessage

from tgcf import storage as st

class AlbumBuffer:
    """Manages buffering and detection of media albums (grouped messages)."""

    def __init__(self):
        self.messages: list["TgcfMessage"] = []
        self.current_group_id: Optional[int] = None

    def add_message(self, tm: "TgcfMessage") -> None:
        """Add a message to the current album buffer."""
        self.messages.append(tm)
        self.current_group_id = tm.message.grouped_id

    def should_flush(self, next_grouped_id: Optional[int]) -> bool:
        """Determine if the current album should be forwarded.

        Returns True when:
        - Buffer has messages AND
        - Next message has different grouped_id (or no grouped_id)
        """
        if not self.messages:
            return False

        if self.current_group_id is None:
            return False

        return next_grouped_id != self.current_group_id

    def is_album(self) -> bool:
        """Check if buffer contains multiple messages (true album)."""
        return len(self.messages) > 1

    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self.messages) == 0

    def clear(self) -> None:
        """Clear all buffered messages and group ID."""
        for tm in self.messages:
            tm.clear()
        self.messages.clear()
        self.current_group_id = None

    def get_messages(self) -> list["TgcfMessage"]:
        """Get all buffered messages."""
        return self.messages


def platform_info():
    nl = "\n"
    return f"""Running tgcf {__version__}\
    \nPython {sys.version.replace(nl,"")}\
    \nOS {os.name}\
    \nPlatform {platform.system()} {platform.release()}\
    \n{platform.architecture()} {platform.processor()}"""


async def send_message(recipient: EntityLike, tm: "TgcfMessage") -> Message:
    """Forward or send a copy, depending on config."""
    client: TelegramClient = tm.client
    if CONFIG.show_forwarded_from:
        try:
            return await client.forward_messages(recipient, tm.message)
        except Exception as err:
            logging.warning(f"Failed to forward message to {recipient}: {err}. Trying anonymous send...")
            # Fallback to anonymous sending
    
    # Anonymous sending (either by config or as fallback)
    if tm.new_file:
        message = await client.send_file(
            recipient, tm.new_file, caption=tm.text, reply_to=tm.reply_to
        )
        return message
    tm.message.text = tm.text
    return await client.send_message(recipient, tm.message, reply_to=tm.reply_to)

async def send_album(client: TelegramClient, album: AlbumBuffer, destinations: list[int]) -> None:
    """Forward or send an album, depending on config."""
    if CONFIG.show_forwarded_from:
        await forward_album(client, album, destinations)
    else:
        await forward_album_anonymous(client, album, destinations)


def cleanup(*files: str) -> None:
    """Delete the file names passed as args."""
    for file in files:
        try:
            os.remove(file)
        except FileNotFoundError:
            logging.info(f"File {file} does not exist, so cant delete it.")


def stamp(file: str, user: str) -> str:
    """Stamp the filename with the datetime, and user info."""
    now = str(datetime.now())
    outf = safe_name(f"{user} {now} {file}")
    try:
        os.rename(file, outf)
        return outf
    except Exception as err:
        logging.warning(f"Stamping file name failed for {file} to {outf}. \n {err}")


def safe_name(string: str) -> str:
    """Return safe file name.

    Certain characters in the file name can cause potential problems in rare scenarios.
    """
    return re.sub(pattern=r"[-!@#$%^&*()\s]", repl="_", string=string)


def match(pattern: str, string: str, regex: bool) -> bool:
    if regex:
        return bool(re.findall(pattern, string))
    return pattern in string


def replace(pattern: str, new: str, string: str, regex: bool) -> str:
    def fmt_repl(matched):
        style = new
        s = STYLE_CODES.get(style)
        return f"{s}{matched.group(0)}{s}"

    if regex:
        if new in STYLE_CODES:
            compliled_pattern = re.compile(pattern)
            return compliled_pattern.sub(repl=fmt_repl, string=string)
        return re.sub(pattern, new, string)
    else:
        return string.replace(pattern, new)


def clean_session_files():
    for item in os.listdir():
        if item.endswith(".session") or item.endswith(".session-journal"):
            os.remove(item)


def get_reply_to_mapping(source_chat_id: int, reply_to_msg_id: int) -> dict[int, int]:
    """Get reply_to message IDs for each destination if reply chain is enabled.
    
    Args:
        source_chat_id: The chat ID where the original message came from
        reply_to_msg_id: The message ID that the original message is replying to
        
    Returns:
        Dict mapping destination chat IDs to their corresponding reply_to message IDs
    """
    if not CONFIG.reply_chain:
        return {}
    
    reply_event = st.DummyEvent(source_chat_id, reply_to_msg_id)
    reply_event_uid = st.EventUid(reply_event)
    
    if reply_event_uid in st.stored:
        return st.stored[reply_event_uid]
    
    return {}


async def forward_album_anonymous(
    client: TelegramClient,
    album: AlbumBuffer,
    destinations: list[int]
) -> None:
    """Send album as new messages without 'Forwarded from' attribution.

    Sends media files as an album while preserving captions.
    """
    messages = album.get_messages()
    if not messages:
        return

    source_chat_id = messages[0].message.chat_id
    first_message = messages[0].message

    # Extract media and captions from album messages
    files_to_send = []
    captions = []

    for tm in messages:
        if tm.message.media:
            files_to_send.append(tm.message.media)
            captions.append(tm.text or "")

    if not files_to_send:
        logging.error(f"Album with {len(messages)} messages has no media. IDs: {[m.message.id for m in messages]}")
        return

    # Check if the first message in album is a reply
    reply_to_mapping = {}
    if first_message.is_reply:
        reply_to_mapping = get_reply_to_mapping(source_chat_id, first_message.reply_to_msg_id)

    for dest in destinations:
        try:
            # Get the correct reply_to for this destination
            reply_to = reply_to_mapping.get(dest, None)

            sent_messages = await client.send_file(
                dest,
                files_to_send,
                caption=captions,
                reply_to=reply_to
            )

            # Ensure sent_messages is a list
            if not isinstance(sent_messages, list):
                sent_messages = [sent_messages]

            if len(sent_messages) != len(messages):
                logging.error(f"Album size mismatch: expected {len(messages)}, got {len(sent_messages)}")
            # Update storage for each sent message
            for tm, sent_msg in zip(messages, sent_messages):
                event_uid = st.EventUid(st.DummyEvent(source_chat_id, tm.message.id))
                if event_uid not in st.stored:
                    st.stored[event_uid] = {}
                st.stored[event_uid][dest] = sent_msg.id

        except Exception as err:
            logging.error(f"Failed to send album to {dest}: {err}")


async def forward_album(
    client: TelegramClient,
    album: AlbumBuffer,
    destinations: list[int]
) -> None:
    """Forward an entire album to destinations.

    Uses native Telegram forward to preserve album structure with 'Forwarded from' tag.
    Falls back to anonymous sending if forwarding fails.
    """
    messages = album.get_messages()
    if not messages:
        return

    source_chat_id = messages[0].message.chat_id
    message_ids = [tm.message.id for tm in messages]

    for dest in destinations:
        try:
            # Forward entire album as a batch
            forwarded = await client.forward_messages(
                dest, message_ids, source_chat_id
            )

            # Ensure forwarded is a list
            if not isinstance(forwarded, list):
                forwarded = [forwarded]

            if len(forwarded) != len(messages):
                logging.error(f"Album size mismatch: expected {len(messages)}, got {len(forwarded)}")
            # Update storage for each message in the album
            for tm, fwd_msg in zip(messages, forwarded):
                event_uid = st.EventUid(st.DummyEvent(source_chat_id, tm.message.id))
                if event_uid not in st.stored:
                    st.stored[event_uid] = {}
                st.stored[event_uid][dest] = fwd_msg.id

        except Exception as err:
            logging.warning(f"Failed to forward album to {dest}: {err}. Trying anonymous send...")
            # Fallback to anonymous sending for this destination only
            await forward_album_anonymous(client, album, [dest])


async def forward_single_message(
    tm: "TgcfMessage",
    destinations: list[int]
) -> None:
    """Forward a single message to destinations.

    Uses send_message utility which respects plugin modifications.
    """
    event_uid = st.EventUid(st.DummyEvent(tm.message.chat_id, tm.message.id))
    if event_uid not in st.stored:
        st.stored[event_uid] = {}

    # Check if original message was a reply
    reply_to_mapping = {}
    if tm.message.is_reply:
        reply_to_mapping = get_reply_to_mapping(tm.message.chat_id, tm.message.reply_to_msg_id)

    for dest in destinations:
        try:
            # Set the correct reply_to for this specific destination
            tm.reply_to = reply_to_mapping.get(dest, None)
            fwded_msg = await send_message(dest, tm)
            st.stored[event_uid][dest] = fwded_msg.id
        except Exception as err:
            logging.error(f"Failed to forward message {tm.message.id} to {dest}: {err}")


def parse_telegram_link(url: str) -> tuple[str | int, int] | None:
    """Parse a Telegram post link into (channel, message_id).

    Supports:
    - Public: https://t.me/channel_username/123
    - Private: https://t.me/c/1234567890/123

    Returns:
        Tuple of (channel_identifier, message_id) or None if invalid
    """
    # TODO: Confirm link formats
    patterns = [
        # Public: https://t.me/channel_name/123 or t.me/channel_name/123
        (r"(?:https?://)?t\.me/([a-zA-Z_][a-zA-Z0-9_]{3,})/(\d+)", False),
        # Private: https://t.me/c/1234567890/123
        (r"(?:https?://)?t\.me/c/(\d+)/(\d+)", True),
    ]

    for pattern, is_private in patterns:
        match = re.match(pattern, url)
        if match:
            channel = match.group(1)
            msg_id = int(match.group(2))
            # For private links, convert to proper channel ID format
            if is_private:
                channel = int(f"-100{channel}")
            return (channel, msg_id)
    return None
