"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

import asyncio
import logging
import time
from typing import List

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.patched import MessageService

from tgcf import config
from tgcf.config import CONFIG, get_SESSION, write_config
from tgcf.plugins import apply_plugins, load_async_plugins
from tgcf.utils import (
    clean_session_files,
    AlbumBuffer,
    forward_album,
    forward_single_message,
    handle_reply_to,
)


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
