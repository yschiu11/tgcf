import logging

from tgcf.plugins import TgcfMessage, TgcfPlugin
from tgcf.utils.text import replace


class TgcfReplace(TgcfPlugin):
    id_ = "replace"

    def __init__(self, data):
        self.replace = data
        logging.info(self.replace)

    def modify(self, wrapped_msg: TgcfMessage) -> TgcfMessage:
        msg_text: str = wrapped_msg.text
        if not msg_text:
            return wrapped_msg
        for original, new in self.replace.text.items():
            msg_text = replace(original, new, msg_text, self.replace.regex)
        wrapped_msg.text = msg_text
        return wrapped_msg
