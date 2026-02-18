import logging
import sys

from telethon import TelegramClient

from tgcf.config import get_SESSION, read_config
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
            get_SESSION(config.login, 'tgcf_sender'),
            config.login.api_id,
            config.login.api_hash,
        )
        if config.login.user_type == 0:
            if config.login.bot_token == "":
                logging.warning("[Sender] Bot token not found, but login type is set to bot.")
                sys.exit()
            await sender.start(bot_token=config.login.bot_token)
        else:
            await sender.start()
        self.sender = sender

    async def modify(self, tm: TgcfMessage) -> TgcfMessage:
        tm.client = self.sender
        if tm.file_type != FileType.NOFILE:
            tm.new_file = await tm.get_file()
            tm.cleanup = True
        return tm