import logging
from dataclasses import dataclass
from enum import Enum, auto

from telethon.tl.custom.message import Message
from telethon.tl.patched import MessageService

from tgcf import const
from tgcf.history import HistoryStore
from tgcf.plugins import apply_plugins
from tgcf.utils.buffer import AlbumBuffer
from tgcf.utils.sender import forward_messages_to_dests


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
    dest_chats: list[int] | None = None
    did_flush: bool = False  # True if an album was flushed


class ForwardingPipeline:
    def __init__(self, client, config, history: HistoryStore):
        self.client = client
        self.config = config
        self.history = history
        self._msg_count = 0
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

        self._msg_count += 1
        if self._msg_count % 100 == 0:
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
            await forward_messages_to_dests(self.client, [wrapped_msg], packet.dest_chats, self.config, self.history)
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
            await forward_messages_to_dests(self.client, messages, dest_chats, self.config, self.history)
        finally:
            for wrapped_msg in messages:
                wrapped_msg.clear()

    async def handle_edit(self, packet: MessagePacket) -> PipelineResult:
        api_msg = packet.raw_message
        src_chat = packet.src_chat

        wrapped_msg = await apply_plugins(api_msg, self.config.plugins)
        if not wrapped_msg:
            return PipelineResult(PipelineStatus.IGNORED)

        dest_map = self.history.get_dest_map(src_chat, api_msg.id)

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

        await forward_messages_to_dests(self.client, [wrapped_msg], packet.dest_chats, self.config, self.history)
        wrapped_msg.clear()
        return PipelineResult(PipelineStatus.SENT)

    async def handle_delete(self, src_chat: int, deleted_ids: list[int]) -> PipelineResult:
        for src_msg in deleted_ids:
            dest_map = self.history.get_dest_map(src_chat, src_msg)
            if dest_map:
                for dest_chat, dest_msg in dest_map.items():
                    if dest_msg is None:
                        continue
                    try:
                        await self.client.delete_messages(dest_chat, dest_msg)
                    except Exception as e:
                        logging.error(f"Failed to delete message {dest_msg} in {dest_chat}: {e}")
        return PipelineResult(PipelineStatus.DELETED)
