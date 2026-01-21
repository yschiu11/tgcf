import logging
import sys

from tgcf.plugins import TgcfMessage, TgcfPlugin
from tgcf.config import read_config, get_SESSION
from telethon import TelegramClient
from tgcf.plugin_models import FileType

class TgcfSender(TgcfPlugin):
    id_ = "sender"
    
    async def __ainit__(self) -> None:
        """Initialize the sender client.
        
        This reads the current config to get login credentials.
        The sender plugin creates a separate client for sending messages.
        """
        config = read_config()
        sender = TelegramClient(
            get_SESSION(self.data, 'tgcf_sender'),
            config.login.API_ID,
            config.login.API_HASH,
        )
        if self.data.user_type == 0:
            if self.data.BOT_TOKEN == "":
                logging.warning("[Sender] Bot token not found, but login type is set to bot.")
                sys.exit()
            await sender.start(bot_token=self.data.BOT_TOKEN)
        else:
            await sender.start()
        self.sender = sender

    async def modify(self, tm: TgcfMessage) -> TgcfMessage:
        tm.client = self.sender
        if tm.file_type != FileType.NOFILE:
            tm.new_file = await tm.get_file()
            tm.cleanup = True
        return tm