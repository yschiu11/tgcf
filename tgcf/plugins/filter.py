import logging

from tgcf.plugin_models import TextFilter
from tgcf.plugins import TgcfMessage, TgcfPlugin
from tgcf.utils.text import match


class TgcfFilter(TgcfPlugin):
    id_ = "filter"

    def __init__(self, data) -> None:
        self.filters = data
        self.case_correct()
        logging.info(self.filters)

    def case_correct(self) -> None:
        textf: TextFilter = self.filters.text

        if textf.case_sensitive is False and textf.regex is False:
            textf.blacklist = [item.lower() for item in textf.blacklist]
            textf.whitelist = [item.lower() for item in textf.whitelist]

    def modify(self, wrapped_msg: TgcfMessage) -> TgcfMessage | None:
        if not self.users_safe(wrapped_msg) or not self.files_safe(wrapped_msg) or not self.text_safe(wrapped_msg):
            return None
        return wrapped_msg

    def text_safe(self, wrapped_msg: TgcfMessage) -> bool:
        flist = self.filters.text
        text = wrapped_msg.text or ""

        if not text and not flist.whitelist:
            return True
        if not flist.case_sensitive:
            text = text.lower()

        # first check if any blacklisted pattern is present
        for forbidden in flist.blacklist:
            if match(forbidden, text, self.filters.text.regex):
                return False  # when a forbidden pattern is found

        if not flist.whitelist:
            return True  # if no whitelist is present

        # if whitelist is present
        for allowed in flist.whitelist:
            if match(allowed, text, self.filters.text.regex):
                return True  # only when atleast one whitelisted pattern is found

        return False

    def users_safe(self, wrapped_msg: TgcfMessage) -> bool:
        flist = self.filters.users
        sender = str(wrapped_msg.sender_id)
        if sender in flist.blacklist:
            return False
        if not flist.whitelist:
            return True
        if sender in flist.whitelist:
            return True
        return False

    def files_safe(self, wrapped_msg: TgcfMessage) -> bool:
        flist = self.filters.files
        fl_type = wrapped_msg.file_type
        if fl_type in flist.blacklist:
            return False
        if not flist.whitelist:
            return True
        if fl_type in flist.whitelist:
            return True
        return False
