"""The module for running tgcf in past mode.

- past mode can only operate with a user account.
- past mode deals with all existing messages.
"""

import asyncio
import logging

from telethon.errors.rpcerrorlist import FloodWaitError

from tgcf.context import TgcfContext
from tgcf.pipeline import MessagePacket


async def forward_job(ctx: TgcfContext) -> None:
    """
    Forward all existing messages in the concerned chats.

    Args:
        ctx: Fully-initialized TgcfContext with client and routing_map mappings
    """
    config = ctx.config
    pipeline = ctx.pipeline

    for src, (forward, dest_chats) in ctx.routing_map.items():
        logging.info(f"Forwarding messages from {src} to {dest_chats}")

        try:
            last_id = forward.offset
            async for message in ctx.client.iter_messages(
                src, reverse=True, offset_id=forward.offset
            ):
                if forward.end and message.id > forward.end:
                    break

                packet = MessagePacket(message, src, dest_chats)

                try:
                    await pipeline.handle_message(packet)

                    if pipeline.is_safe_to_checkpoint(src):
                        forward.offset = message.id

                    last_id = message.id

                    await asyncio.sleep(config.past.delay)
                    logging.info(f"Slept for {config.past.delay} seconds")

                except FloodWaitError as fwe:
                    logging.info(f"Sleeping for {fwe}")
                    await asyncio.sleep(delay=fwe.seconds)
                except Exception as err:
                    logging.exception(err)

            await pipeline.flush(src)
            forward.offset = last_id

        finally:
            logging.info(f"Completed forwarding from {src} to {dest_chats}")
            ctx.save_config()
