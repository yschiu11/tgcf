from __future__ import annotations

"""Telegram message sending, forwarding, and fallback logic."""

import logging
import os
from telethon.client import TelegramClient
from telethon.hints import EntityLike
from telethon.tl.custom.message import Message
from telethon.utils import get_peer_id

from tgcf.config import Config
from tgcf.utils.buffer import fetch_album_by_message
from tgcf.utils.text import parse_telegram_link

from tgcf.plugins import TgcfMessage

# Maps (source_chat_id, source_msg_id) -> {dest_chat_id: dest_msg_id}
ForwardMap = dict[tuple[int, int], dict[int, int | None]]


async def send_message(
    recipient: EntityLike,
    tm: TgcfMessage,
    config: Config,
) -> Message:
    """Send a message to a recipient, forwarding or copying per config.

    If ``config.show_forwarded_from`` is set, attempts a native forward
    first and falls back to an anonymous copy on failure.

    Args:
        recipient: Destination chat.
        tm: Wrapped message to send.
        config: Global forwarding configuration.

    Returns:
        The sent or forwarded ``Message`` object.
    """
    client: TelegramClient = tm.client
    if config.show_forwarded_from:
        try:
            return await client.forward_messages(recipient, tm.message)
        except Exception as err:
            logging.warning(
                f"Failed to forward message to {recipient}: {err}. "
                "Trying anonymous send..."
            )
            # Fallback to anonymous sending

    # Anonymous sending (either by config or as fallback)
    if tm.new_file:
        message = await client.send_file(
            recipient, tm.new_file, caption=tm.text, reply_to=tm.reply_to
        )
        return message
    tm.message.text = tm.text
    return await client.send_message(recipient, tm.message, reply_to=tm.reply_to)


async def send_album(
    client: TelegramClient,
    messages: list[TgcfMessage],
    destinations: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Dispatch an album to destinations via forward or anonymous copy.

    Args:
        client: Telegram client.
        messages: Album messages.
        destinations: Destination chat IDs.
        config: Global forwarding configuration.
        stored: Forward map updated with sent message IDs.
    """
    if config.show_forwarded_from:
        await forward_album(client, messages, destinations, stored)
    else:
        await forward_album_anonymous(client, messages, destinations, config, stored)


def get_reply_to_mapping(
    source_chat_id: int,
    reply_to_msg_id: int,
    config: Config,
    stored: ForwardMap,
) -> dict[int, int | None]:
    """Look up forwarded reply-to IDs for each destination.

    When reply chaining is enabled, maps each destination to the
    message ID that the reply should point to.

    Args:
        source_chat_id: Chat where the original message lives.
        reply_to_msg_id: ID the original message replies to.
        config: Global configuration (checked for ``reply_chain``).
        stored: Forward map with previously sent IDs.

    Returns:
        Mapping of destination chat ID to reply-to message ID,
        or empty dict if reply chaining is disabled or no match.
    """
    if not config.reply_chain:
        return {}

    reply_event_uid = (source_chat_id, reply_to_msg_id)

    if reply_event_uid in stored:
        return stored[reply_event_uid]

    return {}


async def forward_album_anonymous(
    client: TelegramClient,
    messages: list[TgcfMessage],
    destinations: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Re-upload album media as new messages (no 'Forwarded from' tag).

    Args:
        client: Telegram client.
        messages: Album messages.
        destinations: Destination chat IDs.
        config: Global configuration (used for reply chaining).
        stored: Forward map updated with sent message IDs.

    Raises:
        Exception: Propagated from the Telegram API on send failure.
    """
    if not messages:
        return

    source_chat_id = messages[0].message.chat_id
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
            source_chat_id, first_message.reply_to_msg_id, config, stored
        )

    for dest in destinations:
        try:
            reply_to = reply_to_mapping.get(dest, None)

            sent_messages = await client.send_file(
                dest,
                files_to_send,
                caption=captions,
                reply_to=reply_to,
            )

            if not isinstance(sent_messages, list):
                sent_messages = [sent_messages]

            if len(sent_messages) != len(messages):
                logging.error(
                    f"Album size mismatch: expected {len(messages)}, "
                    f"got {len(sent_messages)}"
                )
            # Update storage for each sent message
            for tm, sent_msg in zip(messages, sent_messages):
                event_uid = (source_chat_id, tm.message.id)
                if event_uid not in stored:
                    stored[event_uid] = {}
                stored[event_uid][dest] = sent_msg.id

        except Exception as err:
            logging.error(f"Failed to send album to {dest}: {err}")
            raise


async def forward_album(
    client: TelegramClient,
    messages: list[TgcfMessage],
    destinations: list[int],
    stored: ForwardMap,
) -> None:
    """Forward an album using native Telegram forward (preserves attribution).

    Args:
        client: Telegram client.
        messages: Album messages.
        destinations: Destination chat IDs.
        stored: Forward map updated with forwarded message IDs.
    """
    if not messages:
        return

    source_chat_id = messages[0].message.chat_id
    message_ids = [tm.message.id for tm in messages]

    for dest in destinations:
        try:
            forwarded = await client.forward_messages(dest, message_ids, source_chat_id)

            if not isinstance(forwarded, list):
                forwarded = [forwarded]

            if len(forwarded) != len(messages):
                logging.error(
                    f"Album size mismatch: expected {len(messages)}, "
                    f"got {len(forwarded)}"
                )
            # Update storage for each message in the album
            for tm, fwd_msg in zip(messages, forwarded):
                event_uid = (source_chat_id, tm.message.id)
                if event_uid not in stored:
                    stored[event_uid] = {}
                stored[event_uid][dest] = fwd_msg.id

        except Exception as err:
            logging.warning(
                f"Failed to forward album to {dest}: {err}. Trying anonymous send..."
            )
            # TODO: fallback needs config which we don't have here
            raise


async def forward_single_message(
    tm: TgcfMessage,
    destinations: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Forward a single message to all destinations.

    Respects plugin modifications applied to ``tm`` and maintains
    reply chain mapping in ``stored``.

    Args:
        tm: Wrapped message (may have been modified by plugins).
        destinations: Destination chat IDs.
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

    for dest in destinations:
        try:
            tm.reply_to = reply_to_mapping.get(dest)
            fwded_msg = await send_message(dest, tm, config)
            stored[event_uid][dest] = fwded_msg.id
        except Exception as err:
            logging.error(f"Failed to forward message {tm.message.id} to {dest}: {err}")


async def send_single_message_with_fallback(
    client: TelegramClient,
    message: Message,
    dest: int,
    config: Config,
) -> None:
    """Send a message with download+reupload fallback for protected content.

    Args:
        client: Telegram client.
        message: Raw Telegram message.
        dest: Destination chat ID.
        config: Global forwarding configuration.

    Raises:
        ValueError: If the message is text-only (no media to reupload).
    """
    tm = TgcfMessage(message)
    tm.client = client

    try:
        await send_message(dest, tm, config)
        logging.info(f"Sent message to {dest} (direct)")
        return
    except Exception as err:
        logging.info(
            f"Direct send failed for {dest}: {err}. "
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

        await client.send_file(dest, file_path, caption=message.text)
        logging.info(f"Sent message to {dest} (via download+reupload)")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Cleaned up temp file: {file_path}")


async def send_album_with_fallback(
    client: TelegramClient,
    messages: list[TgcfMessage],
    dest_ids: list[int],
    config: Config,
    stored: ForwardMap,
) -> None:
    """Send an album with download+reupload fallback for protected content.

    Args:
        client: Telegram client.
        messages: Album messages.
        dest_ids: Destination chat IDs.
        config: Global forwarding configuration.
        stored: Forward map updated with sent message IDs.
    """
    if not messages:
        return

    try:
        await forward_album_anonymous(client, messages, dest_ids, config, stored)
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
        for dest in dest_ids:
            try:
                await client.send_file(dest, downloaded_files, caption=captions)
                logging.info(f"Sent album to {dest} (via download+reupload)")
            except Exception as err:
                logging.error(f"Failed to send album via fallback to {dest}: {err}")
    finally:
        for file_path in downloaded_files:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Cleaned up: {file_path}")


async def resolve_dest_ids(
    client: TelegramClient,
    destinations: list[int | str],
) -> list[int]:
    """Resolve a list of destinations to their numeric chat IDs.

    Handles three formats:
    - Integer IDs: Used directly.
    - String numeric IDs: Converted to int (e.g., "-100123456789").
    - Usernames: Resolved via Telegram API (e.g., "@channel_name").

    Args:
        client: Authenticated TelegramClient.
        destinations: List of destination chat IDs or usernames.

    Returns:
        List of resolved numeric chat IDs.
    """
    dest_ids: list[int] = []
    for dest in destinations:
        try:
            if isinstance(dest, int):
                dest_ids.append(dest)
            elif dest.lstrip("-").isdigit():
                dest_ids.append(int(dest))
            else:
                entity = await client.get_entity(dest)
                dest_ids.append(get_peer_id(entity))
        except Exception as err:
            logging.error(f"Failed to resolve destination {dest}: {err}")
            raise
    return dest_ids


async def forward_by_link(
    client: TelegramClient,
    url: str,
    destinations: list[int | str],
    config: Config,
) -> None:
    """Forward a message or album by its Telegram post link.

    Sends as a clean copy (no attribution). Falls back to
    download+reupload for channels with content protection.

    Args:
        client: Authenticated Telegram client.
        url: Telegram post link (``t.me/...``).
        destinations: Destination chat IDs or usernames.
        config: Global forwarding configuration.

    Raises:
        ValueError: If the link is invalid or the message is not found.
    """
    parsed = parse_telegram_link(url)
    if not parsed:
        raise ValueError(f"Invalid Telegram link: {url}")

    channel, msg_id = parsed
    logging.info(f"Parsed link: channel={channel}, msg_id={msg_id}")

    dest_ids = await resolve_dest_ids(client, destinations)

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
        await send_album_with_fallback(client, messages, dest_ids, config, stored)
    else:
        for dest in dest_ids:
            try:
                await send_single_message_with_fallback(client, message, dest, config)
            except Exception as err:
                logging.error(f"Failed to send message to {dest}: {err}")
