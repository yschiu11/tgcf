from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tgcf.context import TgcfContext

from tgcf.utils import AlbumBuffer
from telethon.tl.custom.message import Message
from telethon.tl.patched import MessageService
from dataclasses import dataclass
from tgcf.utils import forward_single_message, send_album
from tgcf.plugins import apply_plugins
from tgcf import const
from enum import Enum, auto
import logging

class MessageHistory:
    def __init__(self):
        self.records: dict[tuple[int, int], dict[int, int | None]] = {}

    def add_placeholder(self, source_chat: int, source_msg: int, dest_chats: list[int]):
        uid = (source_chat, source_msg)
        if uid not in self.records:
            self.records[uid] = {}

        for dest in dest_chats:
            self.records[uid][dest] = None

    def set_sent_id(self, source_chat: int, source_msg: int, dest_chat: int, dest_msg: int):
        uid = (source_chat, source_msg)
        if uid not in self.records:
            self.records[uid] = {}

        self.records[uid][dest_chat] = dest_msg

    def get_dest_msg(self, source_chat_id: int, source_msg: int, dest_chat: int) -> int | None:
        uid = (source_chat_id, source_msg)
        return self.records.get(uid, {}).get(dest_chat)

    def prune(self, limit: int):
        while len(self.records) > limit:
            self.records.pop(next(iter(self.records)))

@dataclass
class MessagePacket:
    raw_message: Message
    source_chat_id: int
    dest_chat_ids: list[int]

class PipelineStatus(Enum):
    SENT = auto()
    BUFFERED = auto()
    FLUSHED = auto()
    IGNORED = auto()
    DELETED = auto()

@dataclass
class PipelineResult:
    status: PipelineStatus
    affected_destinations: list[int] = None
    did_flush: bool = False  # True if an album was flushed


class ForwardingPipeline:
    def __init__(self, client, config, history):
        self.client = client
        self.config = config
        self.history = history
        # map: chat_id -> (Buffer, Destinations)
        self.buffers: dict[int, tuple[AlbumBuffer, list[int]]] = {}

    def is_safe_to_checkpoint(self, chat_id: int) -> bool:
        return chat_id not in self.buffers

    async def handle_message(self, packet: MessagePacket) -> PipelineResult:
        msg = packet.raw_message
        chat_id = packet.source_chat_id
        did_flush = False

        if isinstance(msg, MessageService):
            return PipelineResult(PipelineStatus.IGNORED)

        self.history.prune(const.KEEP_LAST_MANY)

        tm = await apply_plugins(msg, self.config.plugins)
        if not tm:
            return PipelineResult(PipelineStatus.IGNORED)

        if chat_id in self.buffers:
            buffer, _ = self.buffers[chat_id]
            if buffer.should_flush(msg.grouped_id):
                await self._flush_buffer(chat_id)
                did_flush = True

        if msg.grouped_id:
            if chat_id not in self.buffers:
                self.buffers[chat_id] = (AlbumBuffer(), packet.dest_chat_ids)

            buffer, _ = self.buffers[chat_id]
            buffer.add_message(tm)
            self.history.add_placeholder(
                source_chat=chat_id,
                source_msg=msg.id,
                dest_chats=packet.dest_chat_ids
            )

            return PipelineResult(PipelineStatus.BUFFERED, did_flush=did_flush)
        else:
            await forward_single_message(tm, packet.dest_chat_ids, self.config, self.history.records)
            tm.clear()
            return PipelineResult(PipelineStatus.SENT, packet.dest_chat_ids, did_flush)

    async def flush(self, chat_id: int) -> None:
        """Public method for the external timeout task to call."""
        await self._flush_buffer(chat_id)


    async def _flush_buffer(self, chat_id: int) -> None:
        if chat_id not in self.buffers:
            return

        buffer, dests = self.buffers[chat_id]
        messages = buffer.flush()
        del self.buffers[chat_id]

        if not messages:
            return

        try:
            if len(messages) > 1:
                await send_album(self.client, messages, dests, self.config, self.history.records)
            else:
                await forward_single_message(messages[0], dests, self.config, self.history.records)
        finally:
            for tm in messages:
                tm.clear()

    async def handle_edit(self, packet: MessagePacket) -> PipelineResult:
        msg = packet.raw_message
        source_chat_id = packet.source_chat_id

        tm = await apply_plugins(msg, self.config.plugins)
        if not tm:
            return PipelineResult(PipelineStatus.IGNORED)

        event_uid = (source_chat_id, msg.id)
        fwded_ids = self.history.records.get(event_uid)

        if fwded_ids:
            for dest_id, dest_msg_id in fwded_ids.items():
                if dest_msg_id is None:
                    continue
                if self.config.live.delete_on_edit == msg.text:
                    await self.client.delete_messages(dest_id, dest_msg_id)
                else:
                    if msg.media:
                        logging.warning("Media edits are not supported by Telegram API, only text/caption edits are synced")
                    await self.client.edit_message(dest_id, dest_msg_id, text=tm.text)
            tm.clear()
            return PipelineResult(PipelineStatus.SENT)

        await forward_single_message(tm, packet.dest_chat_ids, self.config, self.history.records)
        tm.clear()
        return PipelineResult(PipelineStatus.SENT)

    async def handle_delete(self, chat_id: int, deleted_ids: list[int]) -> PipelineResult:
        for msg_id in deleted_ids:
            event_uid = (chat_id, msg_id)
            fwded_ids = self.history.records.get(event_uid)
            if fwded_ids:
                for dest_id, dest_msg_id in fwded_ids.items():
                    if dest_msg_id is None:
                        continue
                    try:
                        await self.client.delete_messages(dest_id, dest_msg_id)
                    except Exception as e:
                        logging.error(f"Failed to delete message {dest_msg_id} in {dest_id}: {e}")
        return PipelineResult(PipelineStatus.DELETED)