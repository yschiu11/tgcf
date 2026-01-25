"""The module responsible for operating tgcf in live mode."""

import asyncio
import logging

from telethon import TelegramClient, events, functions, types
from telethon.tl.custom.message import Message

from tgcf import const
from tgcf.bot import get_events
from tgcf.context import TgcfContext
from tgcf.plugins import apply_plugins
from tgcf.utils import (
    send_message,
    send_album,
    AlbumBuffer,
    forward_single_message,
)


async def _flush_album(
    ctx: TgcfContext,
    chat_id: int,
    destinations: list[int],
) -> None:
    """Flush the buffered album for a specific chat after timeout."""
    buffer = ctx.album_buffers.get(chat_id)
    if buffer and not buffer.is_empty():
        if buffer.is_album():
            await send_album(ctx.client, buffer, destinations, ctx.config, ctx.stored)
        else:
            tm = buffer.get_messages()[0]
            await forward_single_message(tm, destinations, ctx.config, ctx.stored)
        buffer.clear()

    # Clean up the flush task
    if chat_id in ctx.flush_tasks:
        del ctx.flush_tasks[chat_id]


def _schedule_album_flush(
    ctx: TgcfContext,
    chat_id: int,
    destinations: list[int],
) -> None:
    """Schedule or reschedule the album flush timeout for a chat."""
    timeout = ctx.config.live.album_flush_timeout

    # Cancel existing flush task if any
    if chat_id in ctx.flush_tasks:
        ctx.flush_tasks[chat_id].cancel()

    # Schedule new flush task
    async def _timeout_wrapper():
        try:
            await asyncio.sleep(timeout)
            await _flush_album(ctx, chat_id, destinations)
        except asyncio.CancelledError:
            logging.debug(f"Album flush task cancelled for chat {chat_id}")

    ctx.flush_tasks[chat_id] = asyncio.create_task(_timeout_wrapper())


def make_new_message_handler(ctx: TgcfContext):
    """Factory that creates a new message handler with context closure."""
    
    async def handler(event: Message | events.NewMessage) -> None:
        """Process new incoming messages with album buffering support."""
        chat_id = event.chat_id

        if chat_id not in ctx.from_to:
            return
        logging.info(f"New message received in {chat_id}")
        message = event.message

        event_uid = (chat_id, event.id)

        # Prune old stored entries
        ctx.prune_stored(const.KEEP_LAST_MANY)

        dest = ctx.from_to.get(chat_id)

        tm = await apply_plugins(message, ctx.config.plugins)
        if not tm:
            return

        # Initialize buffer for this chat if needed
        if chat_id not in ctx.album_buffers:
            ctx.album_buffers[chat_id] = AlbumBuffer()

        buffer = ctx.album_buffers[chat_id]

        # Check if we need to flush the current buffer due to group ID change
        if buffer.should_flush(message.grouped_id):
            # Cancel pending flush task to prevent duplicate flush
            if chat_id in ctx.flush_tasks:
                ctx.flush_tasks[chat_id].cancel()
            # Flush existing album before processing new message
            await _flush_album(ctx, chat_id, dest)

        # Add message to buffer
        if message.grouped_id:
            # This message is part of an album, buffer it
            # Pre-create storage entry so edit/delete handlers can find it
            ctx.stored[event_uid] = {}
            buffer.add_message(tm)
            # Schedule flush after timeout in case no more messages arrive
            _schedule_album_flush(ctx, chat_id, dest)
        else:
            # Standalone message, forward immediately
            ctx.stored[event_uid] = {}
            await forward_single_message(tm, dest, ctx.config, ctx.stored)
            tm.clear()

    return handler


def make_edited_message_handler(ctx: TgcfContext):
    """Factory that creates an edited message handler with context closure."""

    async def handler(event) -> None:
        """Handle message edits."""
        message = event.message
        chat_id = event.chat_id

        if chat_id not in ctx.from_to:
            return

        logging.info(f"Message edited in {chat_id}")

        event_uid = (chat_id, event.id)

        tm = await apply_plugins(message, ctx.config.plugins)

        if not tm:
            return

        fwded_msgs = ctx.stored.get(event_uid)

        if fwded_msgs:
            for _, msg in fwded_msgs.items():
                if ctx.config.live.delete_on_edit == message.text:
                    await msg.delete()
                    await message.delete()
                else:
                    await msg.edit(tm.text)
            return

        dest = ctx.from_to.get(chat_id)

        for d in dest:
            await send_message(d, tm, ctx.config)
        tm.clear()

    return handler


def make_deleted_message_handler(ctx: TgcfContext):
    """Factory that creates a deleted message handler with context closure."""

    async def handler(event) -> None:
        """Handle message deletes."""
        chat_id = event.chat_id
        if chat_id not in ctx.from_to:
            return

        logging.info(f"Message deleted in {chat_id}")

        msg_id = getattr(event, "id", None) or getattr(event, "deleted_id", None)
        event_uid = (chat_id, msg_id)
        fwded_msgs = ctx.stored.get(event_uid)
        if fwded_msgs:
            for _, msg in fwded_msgs.items():
                await msg.delete()
            return

    return handler


def get_core_events(ctx: TgcfContext) -> dict:
    """Get core event handlers with context bound via closures."""
    return {
        "new": (make_new_message_handler(ctx), events.NewMessage()),
        "edited": (make_edited_message_handler(ctx), events.MessageEdited()),
        "deleted": (make_deleted_message_handler(ctx), events.MessageDeleted()),
    }


async def start_sync(ctx: TgcfContext) -> None:
    """Start tgcf live sync.
    
    Args:
        ctx: Fully-initialized TgcfContext with client, from_to, and admins
    """
    config = ctx.config
    logging.info(f"ctx.is_bot={ctx.is_bot}")

    all_events = get_core_events(ctx)
    command_events = get_events(ctx)
    all_events.update(command_events)
    for key, val in all_events.items():
        if config.live.delete_sync is False and key == "deleted":
            continue
        ctx.client.add_event_handler(*val)
        logging.info(f"Added event handler for {key}")

    if ctx.is_bot and const.REGISTER_COMMANDS:
        await ctx.client(
            functions.bots.SetBotCommandsRequest(
                scope=types.BotCommandScopeDefault(),
                lang_code="en",
                commands=[
                    types.BotCommand(command=key, description=value)
                    for key, value in const.COMMANDS.items()
                ],
            )
        )

    await ctx.client.run_until_disconnected()
