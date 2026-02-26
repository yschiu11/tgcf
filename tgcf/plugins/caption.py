import logging

from tgcf.plugins import TgcfMessage, TgcfPlugin


class TgcfCaption(TgcfPlugin):
    id_ = "caption"

    def __init__(self, data) -> None:
        self.caption = data
        logging.info(self.caption)

    def modify(self, wrapped_msg: TgcfMessage) -> TgcfMessage:
        wrapped_msg.text = f"{self.caption.header}{wrapped_msg.text or ''}{self.caption.footer}"
        return wrapped_msg
