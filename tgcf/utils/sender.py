from __future__ import annotations

"""Telegram message sending, forwarding, and fallback logic."""

import logging
from pathlib import Path

from telethon.client import TelegramClient
from telethon.tl.custom.message import Message
from telethon.utils import get_peer_id

from tgcf.config import Config
from tgcf.plugins import TgcfMessage
from tgcf.utils.buffer import fetch_album_by_message
from tgcf.utils.text import parse_telegram_link

# Maps (src_chat, src_msg) -> {dest_chat: dest_msg}
ForwardMap = dict[tuple[int, int], dict[int, int | None]]


async def forward_messages_to_dests(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chats: list[int],
    config: Config,
    history_map: ForwardMap,
) -> None:
    """Entry point for forwarding messages to multiple destinations."""
    if not messages:
        return

    for dest_chat in dest_chats:
        await dispatch_payload(client, messages, dest_chat, config, history_map)


async def forward_by_link(
    client: TelegramClient,
    url: str,
    raw_dests: list[int | str],
    config: Config,
) -> None:
    """Forward a message or album by its Telegram post link.

    Sends as a clean copy (no attribution). Falls back to
    download+reupload for channels with content protection.

    Args:
        client: Authenticated Telegram client.
        url: Telegram post link (``t.me/...``).
        raw_dests: Destination chat IDs or usernames.
        config: Global forwarding configuration.

    Raises:
        ValueError: If the link is invalid or the message is not found.
    """
    parsed = parse_telegram_link(url)
    if not parsed:
        raise ValueError(f"Invalid Telegram link: {url}")

    channel, src_msg = parsed
    logging.info(f"Parsed link: channel={channel}, src_msg={src_msg}")

    dest_chats = await resolve_dest_ids(client, raw_dests)

    history_map: ForwardMap = {}

    # Fetch the target message
    message = await client.get_messages(channel, ids=src_msg)
    if not message:
        raise ValueError(f"Message not found: {url}")

    logging.info(f"Fetched message: id={message.id}, grouped_id={message.grouped_id}")

    if message.grouped_id:
        album_buffer = await fetch_album_by_message(client, channel, src_msg, message.grouped_id)
        messages = album_buffer.flush()
    else:
        wrapped_msg = TgcfMessage(message)
        wrapped_msg.client = client
        messages = [wrapped_msg]

    await forward_messages_to_dests(client, messages, dest_chats, config, history_map)


async def dispatch_payload(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chat: int,
    config: Config,
    history_map: ForwardMap,
) -> None:
    """Route a payload through the delivery pipeline until success."""
    if not messages:
        return

    src_chat = messages[0].message.chat_id
    first_msg = messages[0].message

    reply_to_mapping = {}
    if first_msg.is_reply:
        reply_to_mapping = get_reply_to_mapping(src_chat, first_msg.reply_to_msg_id, config, history_map)

    reply_to = reply_to_mapping.get(dest_chat)
    strategies = get_delivery_strategies(config)

    for strategy in strategies:
        try:
            dest_api_msgs = await strategy(client, messages, dest_chat, reply_to)

            if len(dest_api_msgs) != len(messages):
                logging.error(f"Size mismatch in {strategy.__name__}: expected {len(messages)}, got {len(dest_api_msgs)}")

            for src_msg, dest_msg in zip(messages, dest_api_msgs):
                if not dest_msg:
                    continue
                src_uid = (src_chat, src_msg.message.id)
                if src_uid not in history_map:
                    history_map[src_uid] = {}
                history_map[src_uid][dest_chat] = dest_msg.id

            return

        except Exception as err:
            logging.info(f"[{strategy.__name__}] failed for dest {dest_chat}: {err}. Trying next fallback...")

    logging.error(f"CRITICAL: All delivery strategies exhausted for destination {dest_chat}.")


def get_delivery_strategies(config: Config) -> list:
    """Construct the fallback pipeline based on user configuration."""
    strategies = []
    if config.show_forwarded_from:
        strategies.append(strategy_native_forward)
    strategies.append(strategy_anonymous_copy)
    strategies.append(strategy_download_upload)
    return strategies


def get_reply_to_mapping(
    src_chat: int,
    reply_msg: int,
    config: Config,
    history_map: ForwardMap,
) -> dict[int, int | None]:
    """Look up forwarded reply-to IDs for each destination."""
    if not config.reply_chain:
        return {}

    reply_src_uid = (src_chat, reply_msg)
    return history_map.get(reply_src_uid, {})


async def resolve_dest_ids(
    client: TelegramClient,
    raw_dests: list[int | str],
) -> list[int]:
    """Resolve a list of destinations to their numeric chat IDs."""
    dest_chats: list[int] = []
    for raw_dest in raw_dests:
        try:
            if isinstance(raw_dest, int):
                dest_chats.append(raw_dest)
            elif raw_dest.lstrip("-").isdigit():
                dest_chats.append(int(raw_dest))
            else:
                entity = await client.get_entity(raw_dest)
                dest_chats.append(get_peer_id(entity))
        except Exception as err:
            logging.error(f"Failed to resolve destination {raw_dest}: {err}")
            raise
    return dest_chats


async def strategy_native_forward(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chat: int,
    reply_to: int | None,
) -> list[Message]:
    """Tier 1: Native Telegram forward (preserves attribution)."""
    src_chat = messages[0].message.chat_id
    src_msgs = [msg.message.id for msg in messages]

    res = await client.forward_messages(dest_chat, src_msgs, src_chat)
    return res if isinstance(res, list) else [res]


async def strategy_anonymous_copy(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chat: int,
    reply_to: int | None,
) -> list[Message]:
    """Tier 2: Clean copy using existing Telegram file IDs or text."""
    files = []
    captions = []

    for msg in messages:
        # Use plugin-modified file if it exists, otherwise use original media
        media = msg.new_file if msg.new_file else msg.message.media
        if media:
            files.append(media)
        captions.append(msg.text or "")

    if files:
        res = await client.send_file(dest_chat, files, caption=captions, reply_to=reply_to)
        return res if isinstance(res, list) else [res]
    else:
        # Text only (guaranteed to be a single message, Telegram doesn't have text-only albums)
        msg = messages[0]
        msg.message.text = msg.text
        res = await client.send_message(dest_chat, msg.message, reply_to=reply_to)
        return [res]


async def strategy_download_upload(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chat: int,
    reply_to: int | None,
) -> list[Message]:
    """Tier 3: Nuclear fallback for DRM/protected content."""
    downloaded_files = []
    captions = []

    for msg in messages:
        if msg.message.media:
            file_path = await msg.message.download_media("")
            if file_path:
                downloaded_files.append(file_path)
        captions.append(msg.text or "")

    if not downloaded_files:
        raise ValueError("No media to download for fallback, or download failed.")

    try:
        res = await client.send_file(dest_chat, downloaded_files, caption=captions, reply_to=reply_to)
        return res if isinstance(res, list) else [res]
    finally:
        for file_path in downloaded_files:
            Path(file_path).unlink(missing_ok=True)
