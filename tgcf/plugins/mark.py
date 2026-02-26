import logging
import os
import shutil

import requests
from watermark import File, Watermark, apply_watermark

from tgcf.plugin_models import FileType
from tgcf.plugins import TgcfMessage, TgcfPlugin
from tgcf.utils.io import cleanup


def download_image(url: str, filename: str = "image.png") -> bool:
    if filename in os.listdir():
        logging.info("Image for watermarking already exists.")
        return True
    try:
        logging.info(f"Downloading image {url}")
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            logging.info("Got Response 200")
            with open(filename, "wb") as file:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, file)
    except Exception as err:
        logging.error(err)
        return False
    else:
        logging.info("File created image")
        return True


class TgcfMark(TgcfPlugin):
    id_ = "mark"

    def __init__(self, data) -> None:
        self.data = data

    async def modify(self, wrapped_msg: TgcfMessage) -> TgcfMessage:
        if wrapped_msg.file_type not in [FileType.GIF, FileType.VIDEO, FileType.PHOTO]:
            return wrapped_msg
        downloaded_file = await wrapped_msg.get_file()
        base = File(downloaded_file)
        if self.data.image.startswith("https://"):
            download_image(self.data.image)
            overlay = File("image.png")
        else:
            overlay = File(self.data.image)
        wtm = Watermark(overlay, self.data.position)
        wrapped_msg.new_file = apply_watermark(base, wtm, frame_rate=self.data.frame_rate)
        cleanup(downloaded_file)
        wrapped_msg.cleanup = True
        return wrapped_msg
