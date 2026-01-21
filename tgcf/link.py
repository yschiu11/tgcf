"""Forward messages by Telegram post link.

This module provides the entry point for the `tgcf link` command,
which forwards a single message or album by URL instead of message ID.
"""

import logging

from telethon import TelegramClient

from tgcf.config import read_config, ensure_config_exists, get_SESSION
from tgcf.utils import forward_by_link


async def forward_link_job(url: str, destinations: list[str]) -> None:
    """Forward a message or album by its Telegram post link.

    Always sends as a clean copy without 'Forwarded from' attribution.

    Args:
        url: Telegram post link (e.g., https://t.me/channel/123)
        destinations: List of destination chat IDs or usernames
    """
    ensure_config_exists()
    config = read_config()
    
    if config.login.user_type != 1:
        logging.warning(
            "Bot accounts cannot access protected channels or channels where they are not admin. "
            "Use a user account for full access."
        )

    session = get_SESSION(config.login)
    async with TelegramClient(
        session, config.login.API_ID, config.login.API_HASH
    ) as client:
        logging.info(f"Sending message from {url} to {destinations}")

        try:
            await forward_by_link(
                client=client,
                url=url,
                destinations=destinations,
                config=config
            )
            logging.info("Send complete!")
        except ValueError as err:
            logging.error(f"Failed to send: {err}")
            raise
        except Exception as err:
            logging.exception(f"Unexpected error during send: {err}")
            raise
