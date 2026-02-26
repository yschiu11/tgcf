import logging
import sys

from telethon import TelegramClient

from tgcf.config import get_session, read_config
from tgcf.plugin_models import FileType
from tgcf.plugins import TgcfMessage, TgcfPlugin


class TgcfSender(TgcfPlugin):
    id_ = "sender"
    
    async def __ainit__(self) -> None:
        """Initialize the sender client.
        
        This reads the current config to get login credentials.
        The sender plugin creates a separate client for sending messages.
        """
        config = read_config()
        sender = TelegramClient(
            get_session(config.login, 'tgcf_sender'),
            config.login.api_id,
            config.login.api_hash,
        )
        if config.login.user_type == 0:
            if not config.login.bot_token:
                logging.warning("[Sender] Bot token not found, but login type is set to bot.")
                sys.exit(1)
            await sender.start(bot_token=config.login.bot_token)
        else:
            await sender.start()
        self.sender = sender

    async def modify(self, wrapped_msg: TgcfMessage) -> TgcfMessage:
        wrapped_msg.client = self.sender
        if wrapped_msg.file_type != FileType.NOFILE:
            wrapped_msg.new_file = await wrapped_msg.get_file()
            wrapped_msg.cleanup = True
        return wrapped_msg