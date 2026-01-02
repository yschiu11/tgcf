"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

import asyncio
import logging
import time
from typing import List, Optional

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.custom.message import Message
from telethon.tl.patched import MessageService

from tgcf import config
from tgcf import storage as st
from tgcf.config import CONFIG, get_SESSION, write_config
from tgcf.plugins import apply_plugins, load_async_plugins, TgcfMessage
from tgcf.utils import clean_session_files


class AlbumBuffer:
    """Manages buffering and detection of media albums (grouped messages)."""
    
    def __init__(self):
        self.messages: List[TgcfMessage] = []
        self.current_group_id: Optional[int] = None
    
    def add_message(self, tm: TgcfMessage) -> None:
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
    
    def get_messages(self) -> List[TgcfMessage]:
        """Get all buffered messages."""
        return self.messages


async def forward_album(
    client: TelegramClient,
    album: AlbumBuffer,
    destinations: List[int]
) -> None:
    """Forward an entire album to destinations.
    
    Uses native Telegram forward to preserve album structure.
    Updates storage to track forwarded message IDs.
    Note: Plugin modifications are NOT applied to albums (limitation).
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
    tm: TgcfMessage,
    destinations: List[int]
) -> None:
    """Forward a single message to destinations.
    
    Uses send_message utility which respects plugin modifications.
    Updates storage to track forwarded message IDs.
    """
    from tgcf.utils import send_message
    
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
    tm: TgcfMessage,
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


async def process_buffered_messages(
    client: TelegramClient,
    album_buffer: AlbumBuffer,
    destinations: List[int]
) -> None:
    """Process and forward messages from the buffer.
    
    Handles both albums (multiple messages) and single buffered messages.
    Clears the buffer after processing.
    """
    if album_buffer.is_empty():
        return
    
    if album_buffer.is_album():
        # Multiple messages = true album, forward as batch
        await forward_album(client, album_buffer, destinations)
    else:
        # Single message from buffer, forward individually
        tm = album_buffer.get_messages()[0]
        await handle_reply_to(tm, destinations)
        await forward_single_message(tm, destinations)
    
    album_buffer.clear()


async def forward_job() -> None:
    """
    Forward all existing messages in the concerned chats.
    """
    clean_session_files()
    
    # Load async plugins defined in plugin_models
    await load_async_plugins()
    
    if CONFIG.login.user_type != 1:
        logging.warning(
            "You cannot use bot account for tgcf past mode. "
            "Telegram does not allow bots to access chat history."
        )
        return
    
    SESSION = get_SESSION()
    async with TelegramClient(
        SESSION, CONFIG.login.API_ID, CONFIG.login.API_HASH
    ) as client:
        config.from_to = await config.load_from_to(client, config.CONFIG.forwards)
        
        for from_to, forward in zip(config.from_to.items(), config.CONFIG.forwards):
            src, dest = from_to
            last_id = 0
            album_buffer = AlbumBuffer()
            
            logging.info(f"Forwarding messages from {src} to {dest}")
            
            async for message in client.iter_messages(
                src, reverse=True, offset_id=forward.offset
            ):
                # Skip if we've passed the end point
                if forward.end and last_id > forward.end:
                    continue
                
                # Skip service messages
                if isinstance(message, MessageService):
                    continue
                
                try:
                    # Apply plugins to transform the message
                    tm = await apply_plugins(message)
                    if not tm:
                        continue
                    
                    # Check if we should flush the current album buffer
                    if album_buffer.should_flush(message.grouped_id):
                        await process_buffered_messages(client, album_buffer, dest)
                    
                    # Process current message
                    if message.grouped_id:
                        # This message is part of an album, buffer it
                        album_buffer.add_message(tm)
                    else:
                        # This is a standalone message, forward it immediately
                        await handle_reply_to(tm, dest)
                        await forward_single_message(tm, dest)
                        tm.clear()
                    
                    # Update tracking
                    last_id = message.id
                    logging.info(f"Processed message with id = {last_id}")
                    forward.offset = last_id
                    write_config(CONFIG, persist=False)
                    
                    # Rate limiting delay
                    time.sleep(CONFIG.past.delay)
                    logging.info(f"Slept for {CONFIG.past.delay} seconds")
                    
                except FloodWaitError as fwe:
                    logging.info(f"Sleeping for {fwe}")
                    await asyncio.sleep(delay=fwe.seconds)
                except Exception as err:
                    logging.exception(err)
            
            # Forward any remaining buffered album at the end
            await process_buffered_messages(client, album_buffer, dest)
            
            logging.info(f"Completed forwarding from {src} to {dest}")
