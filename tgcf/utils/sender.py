from __future__ import annotations

"""Telegram message sending, forwarding, and fallback logic."""

import logging
import os

from telethon.client import TelegramClient
from telethon.hints import EntityLike
from telethon.tl.custom.message import Message
from telethon.utils import get_peer_id

from tgcf.config import Config
from tgcf.plugins import TgcfMessage
from tgcf.utils.buffer import fetch_album_by_message
from tgcf.utils.text import parse_telegram_link

# Maps (src_chat, src_msg) -> {dest_chat: dest_msg}
ForwardMap = dict[tuple[int, int], dict[int, int | None]]


async def send_message(
    dest_chat: EntityLike,
    tm: TgcfMessage,
    config: Config,
) -> Message:
    """Send a message to a recipient, forwarding or copying per config.

    If ``config.show_forwarded_from`` is set, attempts a native forward
    first and falls back to an anonymous copy on failure.

    Args:
        dest_chat: Destination chat.
        tm: Wrapped message to send.
        config: Global forwarding configuration.

    Returns:
        The sent or forwarded ``Message`` object.
    """
    client: TelegramClient = tm.client
    if config.show_forwarded_from:
        try:
            return await client.forward_messages(dest_chat, tm.message)
        except Exception as err:
            logging.warning(
                f"Failed to forward message to {dest_chat}: {err}. "
                "Trying anonymous send..."
            )
            # Fallback to anonymous sending

    # Anonymous sending (either by config or as fallback)
    if tm.new_file:
        dest_obj = await client.send_file(
            dest_chat, tm.new_file, caption=tm.text, reply_to=tm.reply_to
        )
        return dest_obj
    tm.message.text = tm.text
    return await client.send_message(dest_chat, tm.message, reply_to=tm.reply_to)


async def send_album(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chats: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Dispatch an album to destinations via forward or anonymous copy.

    Args:
        client: Telegram client.
        messages: Album messages.
        dest_chats: Destination chat IDs.
        config: Global forwarding configuration.
        stored: Forward map updated with sent message IDs.
    """
    if config.show_forwarded_from:
        await forward_album(client, messages, dest_chats, stored)
    else:
        await forward_album_anonymous(client, messages, dest_chats, config, stored)


def get_reply_to_mapping(
    src_chat: int,
    reply_to_msg_id: int,
    config: Config,
    stored: ForwardMap,
) -> dict[int, int | None]:
    """Look up forwarded reply-to IDs for each destination.

    When reply chaining is enabled, maps each destination to the
    message ID that the reply should point to.

    Args:
        src_chat: Chat where the original message lives.
        reply_to_msg_id: ID the original message replies to.
        config: Global configuration (checked for ``reply_chain``).
        stored: Forward map with previously sent IDs.

    Returns:
        Mapping of destination chat ID to reply-to message ID,
        or empty dict if reply chaining is disabled or no match.
    """
    if not config.reply_chain:
        return {}

    reply_event_uid = (src_chat, reply_to_msg_id)

    if reply_event_uid in stored:
        return stored[reply_event_uid]

    return {}


async def forward_album_anonymous(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chats: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Re-upload album media as new messages (no 'Forwarded from' tag).

    Args:
        client: Telegram client.
        messages: Album messages.
        dest_chats: Destination chat IDs.
        config: Global configuration (used for reply chaining).
        stored: Forward map updated with sent message IDs.

    Raises:
        Exception: Propagated from the Telegram API on send failure.
    """
    if not messages:
        return

    src_chat = messages[0].message.chat_id
    first_message = messages[0].message

    files_to_send = []
    captions = []

    for tm in messages:
        if tm.message.media:
            files_to_send.append(tm.message.media)
            captions.append(tm.text or "")

    if not files_to_send:
        logging.error(
            f"Album with {len(messages)} messages has no media. "
            f"IDs: {[m.message.id for m in messages]}"
        )
        return

    # Check if the first message in album is a reply
    reply_to_mapping: dict[int, int | None] = {}
    if first_message.is_reply:
        reply_to_mapping = get_reply_to_mapping(
            src_chat, first_message.reply_to_msg_id, config, stored
        )

    for dest_chat in dest_chats:
        try:
            reply_to = reply_to_mapping.get(dest_chat, None)

            dest_objs = await client.send_file(
                dest_chat,
                files_to_send,
                caption=captions,
                reply_to=reply_to,
            )

            if not isinstance(dest_objs, list):
                dest_objs = [dest_objs]

            if len(dest_objs) != len(messages):
                logging.error(
                    f"Album size mismatch: expected {len(messages)}, "
                    f"got {len(dest_objs)}"
                )
            # Update storage for each sent message
            for tm, dest_obj in zip(messages, dest_objs):
                event_uid = (src_chat, tm.message.id)
                if event_uid not in stored:
                    stored[event_uid] = {}
                stored[event_uid][dest_chat] = dest_obj.id

        except Exception as err:
            logging.error(f"Failed to send album to {dest_chat}: {err}")
            raise


async def forward_album(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chats: list[int],
    stored: ForwardMap,
) -> None:
    """Forward an album using native Telegram forward (preserves attribution).

    Args:
        client: Telegram client.
        messages: Album messages.
        dest_chats: Destination chat IDs.
        stored: Forward map updated with forwarded message IDs.
    """
    if not messages:
        return

    src_chat = messages[0].message.chat_id
    message_ids = [tm.message.id for tm in messages]

    for dest_chat in dest_chats:
        try:
            dest_objs = await client.forward_messages(dest_chat, message_ids, src_chat)

            if not isinstance(dest_objs, list):
                dest_objs = [dest_objs]

            if len(dest_objs) != len(messages):
                logging.error(
                    f"Album size mismatch: expected {len(messages)}, "
                    f"got {len(dest_objs)}"
                )
            # Update storage for each message in the album
            for tm, dest_obj in zip(messages, dest_objs):
                event_uid = (src_chat, tm.message.id)
                if event_uid not in stored:
                    stored[event_uid] = {}
                stored[event_uid][dest_chat] = dest_obj.id

        except Exception as err:
            logging.warning(
                f"Failed to forward album to {dest_chat}: {err}. Trying anonymous send..."
            )
            # TODO: fallback needs config which we don't have here
            raise


async def forward_single_message(
    tm: TgcfMessage,
    dest_chats: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Forward a single message to all destinations.

    Respects plugin modifications applied to ``tm`` and maintains
    reply chain mapping in ``stored``.

    Args:
        tm: Wrapped message (may have been modified by plugins).
        dest_chats: Destination chat IDs.
        config: Global forwarding configuration.
        stored: Forward map updated with sent message IDs.
    """
    event_uid = (tm.message.chat_id, tm.message.id)
    if event_uid not in stored:
        stored[event_uid] = {}

    reply_to_mapping: dict[int, int | None] = {}
    if tm.message.is_reply:
        reply_to_mapping = get_reply_to_mapping(
            tm.message.chat_id, tm.message.reply_to_msg_id, config, stored
        )

    for dest_chat in dest_chats:
        try:
            tm.reply_to = reply_to_mapping.get(dest_chat)
            dest_obj = await send_message(dest_chat, tm, config)
            stored[event_uid][dest_chat] = dest_obj.id
        except Exception as err:
            logging.error(f"Failed to forward message {tm.message.id} to {dest_chat}: {err}")


async def send_single_message_with_fallback(
    client: TelegramClient,
    message: Message,
    dest_chat: int,
    config: Config,
) -> None:
    """Send a message with download+reupload fallback for protected content.

    Args:
        client: Telegram client.
        message: Raw Telegram message.
        dest_chat: Destination chat ID.
        config: Global forwarding configuration.

    Raises:
        ValueError: If the message is text-only (no media to reupload).
    """
    tm = TgcfMessage(message)
    tm.client = client

    try:
        await send_message(dest_chat, tm, config)
        logging.info(f"Sent message to {dest_chat} (direct)")
        return
    except Exception as err:
        logging.info(
            f"Direct send failed for {dest_chat}: {err}. "
            "Falling back to download+reupload."
        )

    # Fallback: download and re-upload
    if not message.media:
        raise ValueError("Cannot use download fallback for text-only messages")

    file_path = None
    try:
        file_path = await message.download_media("")
        if not file_path:
            raise ValueError("Failed to download media")

        logging.info(f"Downloaded media to {file_path}")

        await client.send_file(dest_chat, file_path, caption=message.text)
        logging.info(f"Sent message to {dest_chat} (via download+reupload)")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Cleaned up temp file: {file_path}")


async def send_album_with_fallback(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_chats: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Send an album with download+reupload fallback for protected content.

    Args:
        client: Telegram client.
        messages: Album messages.
        dest_chats: Destination chat IDs.
        config: Global forwarding configuration.
        stored: Forward map updated with sent message IDs.
    """
    if not messages:
        return

    try:
        await forward_album_anonymous(client, messages, dest_chats, config, stored)
        logging.info("Sent album to destinations (direct)")
        return
    except Exception as err:
        logging.info(
            f"Protected content detected, falling back to download+reupload: {err}"
        )

    # Fallback: download all media and re-upload
    captions = [tm.text or "" for tm in messages if tm.message.media]
    downloaded_files: list[str] = []
    try:
        for tm in messages:
            if tm.message.media:
                file_path = await tm.message.download_media("")
                if file_path:
                    downloaded_files.append(file_path)
                    logging.info(f"Downloaded: {file_path}")

        if not downloaded_files:
            logging.error("Failed to download any media for album")
            raise ValueError("Failed to download any media for album")

        # Re-upload as new album to all destinations
        for dest_chat in dest_chats:
            try:
                await client.send_file(dest_chat, downloaded_files, caption=captions)
                logging.info(f"Sent album to {dest_chat} (via download+reupload)")
            except Exception as err:
                logging.error(f"Failed to send album via fallback to {dest_chat}: {err}")
    finally:
        for file_path in downloaded_files:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Cleaned up: {file_path}")


async def resolve_dest_ids(
    client: TelegramClient,
    raw_dests: list[int | str],
) -> list[int]:
    """Resolve a list of destinations to their numeric chat IDs.

    Handles three formats:
    - Integer IDs: Used directly.
    - String numeric IDs: Converted to int (e.g., "-100123456789").
    - Usernames: Resolved via Telegram API (e.g., "@channel_name").

    Args:
        client: Authenticated TelegramClient.
        raw_dests: List of destination chat IDs or usernames.

    Returns:
        List of resolved numeric chat IDs.
    """
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

    channel, msg_id = parsed
    logging.info(f"Parsed link: channel={channel}, msg_id={msg_id}")

    dest_chats = await resolve_dest_ids(client, raw_dests)

    stored: ForwardMap = {}

    # Fetch the target message
    message = await client.get_messages(channel, ids=msg_id)
    if not message:
        raise ValueError(f"Message not found: {url}")

    logging.info(f"Fetched message: id={message.id}, grouped_id={message.grouped_id}")

    if message.grouped_id:
        album_buffer = await fetch_album_by_message(
            client, channel, msg_id, message.grouped_id
        )

        messages = album_buffer.flush()
        await send_album_with_fallback(client, messages, dest_chats, config, stored)
    else:
        for dest_chat in dest_chats:
            try:
                await send_single_message_with_fallback(client, message, dest_chat, config)
            except Exception as err:
                logging.error(f"Failed to send message to {dest_chat}: {err}")
