"""Utility functions to smoothen your life."""

import logging
import os
import platform
import re
import sys
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from telethon.client import TelegramClient
from telethon.hints import EntityLike
from telethon.tl.custom.message import Message

from tgcf import __version__
from tgcf.config import CONFIG
from tgcf.plugin_models import STYLE_CODES

if TYPE_CHECKING:
    from tgcf.plugins import TgcfMessage

from tgcf import storage as st


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
        return await client.forward_messages(recipient, tm.message)
    if tm.new_file:
        message = await client.send_file(
            recipient, tm.new_file, caption=tm.text, reply_to=tm.reply_to
        )
        return message
    tm.message.text = tm.text
    return await client.send_message(recipient, tm.message, reply_to=tm.reply_to)


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


class AlbumBuffer:
    """Manages buffering and detection of media albums (grouped messages)."""

    def __init__(self):
        self.messages: List["TgcfMessage"] = []
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

    def get_messages(self) -> List["TgcfMessage"]:
        """Get all buffered messages."""
        return self.messages


async def forward_album(
    client: TelegramClient,
    album: AlbumBuffer,
    destinations: List[int]
) -> None:
    """Forward an entire album to destinations.

    Uses native Telegram forward to preserve album structure.
    Note: Plugin modifications are NOT applied to albums.
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

            # Update storage for each message in the album
            for tm, fwd_msg in zip(messages, forwarded):
                event_uid = st.EventUid(st.DummyEvent(source_chat_id, tm.message.id))
                if event_uid not in st.stored:
                    st.stored[event_uid] = {}
                st.stored[event_uid][dest] = fwd_msg.id

        except Exception as err:
            logging.error(f"Failed to forward album to {dest}: {err}")


async def forward_single_message(
    tm: "TgcfMessage",
    destinations: List[int]
) -> None:
    """Forward a single message to destinations.

    Uses send_message utility which respects plugin modifications.
    """
    event_uid = st.EventUid(st.DummyEvent(tm.message.chat_id, tm.message.id))
    if event_uid not in st.stored:
        st.stored[event_uid] = {}

    for dest in destinations:
        try:
            fwded_msg = await send_message(dest, tm)
            st.stored[event_uid][dest] = fwded_msg.id
        except Exception as err:
            logging.error(f"Failed to forward message {tm.message.id} to {dest}: {err}")


async def handle_reply_to(
    tm: "TgcfMessage",
    destinations: List[int]
) -> None:
    """Set up reply_to for forwarded message if original was a reply."""
    if not tm.message.is_reply:
        return

    reply_event = st.DummyEvent(tm.message.chat_id, tm.message.reply_to_msg_id)
    reply_event_uid = st.EventUid(reply_event)

    # Only set reply_to if we've previously forwarded the message being replied to
    if reply_event_uid in st.stored:
        # Try to set reply for each destination
        for dest in destinations:
            if dest in st.stored[reply_event_uid]:
                tm.reply_to = st.stored[reply_event_uid][dest]
                break  # Use first available reply reference
