"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

import asyncio
import logging

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.patched import MessageService

from tgcf.context import TgcfContext
from tgcf.plugins import apply_plugins
from tgcf.utils import (
    AlbumBuffer,
    send_album,
    forward_single_message,
)


async def process_buffered_messages(
    ctx: TgcfContext,
    album_buffer: AlbumBuffer,
    destinations: list[int]
) -> None:
    """Process and forward messages from the buffer.

    Handles both albums (multiple messages) and single buffered messages.
    Clears the buffer after processing.
    
    Args:
        ctx: TgcfContext with config and stored
        album_buffer: Buffer containing messages to forward
        destinations: List of destination chat IDs
    """
    messages = album_buffer.flush()
    if not messages:
        return

    try:
        if len(messages) > 1:
            await send_album(ctx.client, messages, destinations, ctx.config, ctx.stored)
        else:
            tm = messages[0]
            await forward_single_message(tm, destinations, ctx.config, ctx.stored)
    finally:
        for tm in messages:
            tm.clear()


async def forward_job(ctx: TgcfContext) -> None:
    """
    Forward all existing messages in the concerned chats.
    
    Args:
        ctx: Fully-initialized TgcfContext with client and from_to mappings
    """
    config = ctx.config

    for from_to, forward in zip(ctx.from_to.items(), config.forwards):
        src, dest = from_to
        album_buffer = AlbumBuffer()

        logging.info(f"Forwarding messages from {src} to {dest}")

        try:
            async for message in ctx.client.iter_messages(
                src, reverse=True, offset_id=forward.offset
            ):
                if forward.end and message.id > forward.end:
                    break

                # Skip service messages
                if isinstance(message, MessageService):
                    continue

                try:
                    # Apply plugins to transform the message
                    tm = await apply_plugins(message, config.plugins)
                    if not tm:
                        continue

                    # Check if we should flush the current album buffer
                    if album_buffer.should_flush(message.grouped_id):
                        await process_buffered_messages(ctx, album_buffer, dest)

                    # Process current message
                    if message.grouped_id:
                        # This message is part of an album, buffer it
                        album_buffer.add_message(tm)
                    else:
                        # This is a standalone message, forward it immediately
                        await forward_single_message(tm, dest, ctx.config, ctx.stored)
                        tm.clear()

                    # Update tracking in memory; persisted in finally block
                    forward.offset = message.id

                    # Rate limiting delay
                    await asyncio.sleep(config.past.delay)
                    logging.info(f"Slept for {config.past.delay} seconds")

                except FloodWaitError as fwe:
                    logging.info(f"Sleeping for {fwe}")
                    await asyncio.sleep(delay=fwe.seconds)
                except Exception as err:
                    logging.exception(err)
        finally:
            # Forward any remaining buffered album at the end
            await process_buffered_messages(ctx, album_buffer, dest)

            logging.info(f"Completed forwarding from {src} to {dest}")

            ctx.save_config()
