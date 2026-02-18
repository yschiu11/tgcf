from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field
from watermark import Position


class FileType(str, Enum):
    AUDIO = "audio"
    GIF = "gif"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"
    STICKER = "sticker"
    CONTACT = "contact"
    PHOTO = "photo"
    DOCUMENT = "document"
    NOFILE = "nofile"


class FilterList(BaseModel):
    blacklist: List[str] = []
    whitelist: List[str] = []


class FilesFilterList(BaseModel):
    blacklist: List[FileType] = []
    whitelist: List[FileType] = []


class TextFilter(FilterList):
    case_sensitive: bool = False
    regex: bool = False


class Style(str, Enum):
    BOLD = "bold"
    ITALICS = "italics"
    CODE = "code"
    STRIKE = "strike"
    PLAIN = "plain"
    PRESERVE = "preserve"


STYLE_CODES = {"bold": "**", "italics": "__", "code": "`", "strike": "~~", "plain": ""}

# define plugin configs


class Filters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(False, alias="check")
    users: FilterList = FilterList()
    files: FilesFilterList = FilesFilterList()
    text: TextFilter = TextFilter()


class Format(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(False, alias="check")
    style: Style = Style.PRESERVE


class MarkConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(False, alias="check")
    image: str = "image.png"
    position: Position = Position.centre
    frame_rate: int = 15


class OcrConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(False, alias="check")


class Replace(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(False, alias="check")
    text: Dict[str, str] = {}
    text_raw: str = ""
    regex: bool = False


class Caption(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool = Field(False, alias="check")
    header: str = ""
    footer: str = ""

class Sender(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = Field(False, alias="check")
    user_type: int = 0  # 0:bot, 1:user
    bot_token: str = Field("", alias="BOT_TOKEN")
    session_string: str = Field("", alias="SESSION_STRING")

class PluginConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    filter: Filters = Filters()
    format: Format = Field(Format(), alias="fmt")
    mark: MarkConfig = MarkConfig()
    ocr: OcrConfig = OcrConfig()
    replace: Replace = Replace()
    caption: Caption = Caption()
    sender: Sender = Sender()


# List of plugins that need to load asynchronously
ASYNC_PLUGIN_IDS = ['sender']