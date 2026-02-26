import pytesseract
from PIL import Image

from tgcf.plugin_models import FileType
from tgcf.plugins import TgcfMessage, TgcfPlugin
from tgcf.utils.io import cleanup


class TgcfOcr(TgcfPlugin):
    id_ = "ocr"

    def __init__(self, data) -> None:
        pass

    async def modify(self, wrapped_msg: TgcfMessage) -> TgcfMessage:

        if wrapped_msg.file_type != FileType.PHOTO:
            return wrapped_msg

        file = await wrapped_msg.get_file()
        wrapped_msg.text = pytesseract.image_to_string(Image.open(file))
        cleanup(file)
        return wrapped_msg
