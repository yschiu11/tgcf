"""The module responsible for operating tgcf in live mode."""

import asyncio
import logging

from telethon import events, functions, types
from telethon.tl.custom.message import Message

from tgcf import const
from tgcf.bot import get_events
from tgcf.context import TgcfContext
from tgcf.pipeline import MessagePacket, PipelineStatus


async def _schedule_album_flush(ctx: TgcfContext, src_chat: int) -> None:
    """Schedule or reschedule the album flush timeout for a chat."""
    timeout = ctx.config.live.album_flush_timeout

    # Cancel existing flush task if any
    if src_chat in ctx.flush_tasks:
        ctx.flush_tasks[src_chat].cancel()

    # Schedule new flush task
    async def _timeout_wrapper():
        try:
            await asyncio.sleep(timeout)
            await ctx.pipeline.flush(src_chat)
        except asyncio.CancelledError:
            logging.debug(f"Flush cancelled for chat {src_chat}")
            raise
        finally:
            if ctx.flush_tasks.get(src_chat) == asyncio.current_task():
                del ctx.flush_tasks[src_chat]

    ctx.flush_tasks[src_chat] = asyncio.create_task(_timeout_wrapper())


def make_new_message_handler(ctx: TgcfContext):
    """Factory that creates a new message handler with context closure."""

    async def handler(new_msg_event: Message | events.NewMessage) -> None:
        """Process new incoming messages with album buffering support."""
        src_chat = new_msg_event.chat_id

        if src_chat not in ctx.from_to:
            return
        logging.info(f"New message received in {src_chat}")

        _, dest_chats = ctx.from_to[src_chat]

        packet = MessagePacket(
            raw_message=new_msg_event.message,
            src_chat=src_chat,
            dest_chats=dest_chats
        )

        result = await ctx.pipeline.handle_message(packet)

        if result.did_flush and src_chat in ctx.flush_tasks:
            ctx.flush_tasks[src_chat].cancel()
            del ctx.flush_tasks[src_chat]

        if result.status == PipelineStatus.BUFFERED:
            await _schedule_album_flush(ctx, src_chat)

    return handler


def make_edited_message_handler(ctx: TgcfContext):
    """Factory that creates an edited message handler with context closure."""

    async def handler(edit_msg_event) -> None:
        """Handle message edits."""
        src_chat = edit_msg_event.chat_id

        if src_chat not in ctx.from_to:
            return

        logging.info(f"Message edited in {src_chat}")
        _, dest_chats = ctx.from_to[src_chat]

        packet = MessagePacket(
            raw_message=edit_msg_event.message,
            src_chat=src_chat,
            dest_chats=dest_chats
        )

        await ctx.pipeline.handle_edit(packet)

    return handler


def make_deleted_message_handler(ctx: TgcfContext):
    """Factory that creates a deleted message handler with context closure."""

    async def handler(del_msg_event) -> None:
        """Handle message deletes."""
        src_chat = del_msg_event.chat_id
        if src_chat not in ctx.from_to:
            return

        logging.info(f"Message deleted in {src_chat}")

        # Telethon's MessageDeleted can have .deleted_ids (list) or .deleted_id (int)
        deleted_ids = getattr(del_msg_event, "deleted_ids", None) or [getattr(del_msg_event, "deleted_id", None)]

        # Filter for valid integers only
        deleted_msgs = [i for i in deleted_ids if isinstance(i, int)]

        if not deleted_msgs:
            return

        await ctx.pipeline.handle_delete(src_chat, deleted_msgs)

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
