import logging

from tgcf.plugin_models import STYLE_CODES, Style
from tgcf.plugins import TgcfMessage, TgcfPlugin


class TgcfFmt(TgcfPlugin):
    id_ = "fmt"

    def __init__(self, data) -> None:
        self.format = data
        logging.info(self.format)

    def modify(self, wrapped_msg: TgcfMessage) -> TgcfMessage:
        if self.format.style is Style.PRESERVE:
            return wrapped_msg
        msg_text: str = wrapped_msg.raw_text
        if not msg_text:
            return wrapped_msg
        style = STYLE_CODES.get(self.format.style)
        wrapped_msg.text = f"{style}{msg_text}{style}"
        return wrapped_msg
