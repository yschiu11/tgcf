import pytesseract
from PIL import Image

from tgcf.plugin_models import FileType
from tgcf.plugins import TgcfMessage, TgcfPlugin
from tgcf.utils.io import cleanup


class TgcfOcr(TgcfPlugin):
    id_ = "ocr"

    def __init__(self, data) -> None:
        pass

    async def modify(self, tm: TgcfMessage) -> TgcfMessage:

        if tm.file_type != FileType.PHOTO:
            return tm

        file = await tm.get_file()
        tm.text = pytesseract.image_to_string(Image.open(file))
        cleanup(file)
        return tm
