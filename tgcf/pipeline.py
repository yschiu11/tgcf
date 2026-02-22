import logging
from dataclasses import dataclass
from enum import Enum, auto

from telethon.tl.custom.message import Message
from telethon.tl.patched import MessageService

from tgcf import const
from tgcf.plugins import apply_plugins
from tgcf.utils.buffer import AlbumBuffer
from tgcf.utils.sender import forward_single_message, send_album


class MessageHistory:
    def __init__(self):
        self.records: dict[tuple[int, int], dict[int, int | None]] = {}

    def add_placeholder(self, src_chat: int, src_msg: int, dest_chats: list[int]):
        src_uid = (src_chat, src_msg)
        if src_uid not in self.records:
            self.records[src_uid] = {}

        for dest_chat in dest_chats:
            self.records[src_uid][dest_chat] = None

    def set_sent_id(self, src_chat: int, src_msg: int, dest_chat: int, dest_msg: int):
        src_uid = (src_chat, src_msg)
        if src_uid not in self.records:
            self.records[src_uid] = {}

        self.records[src_uid][dest_chat] = dest_msg

    def get_dest_msg(self, src_chat: int, src_msg: int, dest_chat: int) -> int | None:
        src_uid = (src_chat, src_msg)
        return self.records.get(src_uid, {}).get(dest_chat)

    def prune(self, limit: int):
        while len(self.records) > limit:
            self.records.pop(next(iter(self.records)))

@dataclass
class MessagePacket:
    raw_message: Message
    src_chat: int
    dest_chats: list[int]

class PipelineStatus(Enum):
    SENT = auto()
    BUFFERED = auto()
    FLUSHED = auto()
    IGNORED = auto()
    DELETED = auto()

@dataclass
class PipelineResult:
    status: PipelineStatus
    dest_chats: list[int] = None
    did_flush: bool = False  # True if an album was flushed


class ForwardingPipeline:
    def __init__(self, client, config, history):
        self.client = client
        self.config = config
        self.history = history
        # map: src_chat -> (Buffer, DestChats)
        self.buffers: dict[int, tuple[AlbumBuffer, list[int]]] = {}

    def is_safe_to_checkpoint(self, src_chat: int) -> bool:
        return src_chat not in self.buffers

    async def handle_message(self, packet: MessagePacket) -> PipelineResult:
        api_msg = packet.raw_message
        src_chat = packet.src_chat
        did_flush = False

        if isinstance(api_msg, MessageService):
            return PipelineResult(PipelineStatus.IGNORED)

        self.history.prune(const.KEEP_LAST_MANY)

        wrapped_msg = await apply_plugins(api_msg, self.config.plugins)
        if not wrapped_msg:
            return PipelineResult(PipelineStatus.IGNORED)

        if src_chat in self.buffers:
            buffer, _ = self.buffers[src_chat]
            if buffer.should_flush(api_msg.grouped_id):
                await self._flush_buffer(src_chat)
                did_flush = True

        if api_msg.grouped_id:
            if src_chat not in self.buffers:
                self.buffers[src_chat] = (AlbumBuffer(), packet.dest_chats)

            buffer, _ = self.buffers[src_chat]
            buffer.add_message(wrapped_msg)
            self.history.add_placeholder(
                src_chat=src_chat,
                src_msg=api_msg.id,
                dest_chats=packet.dest_chats
            )

            return PipelineResult(PipelineStatus.BUFFERED, did_flush=did_flush)
        else:
            await forward_single_message(wrapped_msg, packet.dest_chats, self.config, self.history.records)
            wrapped_msg.clear()
            return PipelineResult(PipelineStatus.SENT, packet.dest_chats, did_flush)

    async def flush(self, src_chat: int) -> None:
        """Public method for the external timeout task to call."""
        await self._flush_buffer(src_chat)


    async def _flush_buffer(self, src_chat: int) -> None:
        if src_chat not in self.buffers:
            return

        buffer, dest_chats = self.buffers[src_chat]
        messages = buffer.flush()
        del self.buffers[src_chat]

        if not messages:
            return

        try:
            if len(messages) > 1:
                await send_album(self.client, messages, dest_chats, self.config, self.history.records)
            else:
                await forward_single_message(messages[0], dest_chats, self.config, self.history.records)
        finally:
            for wrapped_msg in messages:
                wrapped_msg.clear()

    async def handle_edit(self, packet: MessagePacket) -> PipelineResult:
        api_msg = packet.raw_message
        src_chat = packet.src_chat

        wrapped_msg = await apply_plugins(api_msg, self.config.plugins)
        if not wrapped_msg:
            return PipelineResult(PipelineStatus.IGNORED)

        src_uid = (src_chat, api_msg.id)
        dest_map = self.history.records.get(src_uid)

        if dest_map:
            for dest_chat, dest_msg in dest_map.items():
                if dest_msg is None:
                    continue
                if self.config.live.delete_on_edit == api_msg.text:
                    await self.client.delete_messages(dest_chat, dest_msg)
                else:
                    if api_msg.media:
                        logging.warning("Media edits are not supported by Telegram API, only text/caption edits are synced")
                    await self.client.edit_message(dest_chat, dest_msg, text=wrapped_msg.text)
            wrapped_msg.clear()
            return PipelineResult(PipelineStatus.SENT)

        await forward_single_message(wrapped_msg, packet.dest_chats, self.config, self.history.records)
        wrapped_msg.clear()
        return PipelineResult(PipelineStatus.SENT)

    async def handle_delete(self, src_chat: int, deleted_ids: list[int]) -> PipelineResult:
        for src_msg in deleted_ids:
            src_uid = (src_chat, src_msg)
            dest_map = self.history.records.get(src_uid)
            if dest_map:
                for dest_chat, dest_msg in dest_map.items():
                    if dest_msg is None:
                        continue
                    try:
                        await self.client.delete_messages(dest_chat, dest_msg)
                    except Exception as e:
                        logging.error(f"Failed to delete message {dest_msg} in {dest_chat}: {e}")
        return PipelineResult(PipelineStatus.DELETED)