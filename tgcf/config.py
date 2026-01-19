"""Load all user defined config and env vars."""

import logging
import os
import sys
from typing import Dict, List, Optional, Union, Any
import tempfile

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator  # pylint: disable=no-name-in-module
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession

from tgcf import storage as stg
from tgcf.const import CONFIG_FILE_NAME
from tgcf.plugin_models import PluginConfig

pwd = os.getcwd()
env_file = os.path.join(pwd, ".env")

load_dotenv(env_file)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or incomplete."""
    pass


class Forward(BaseModel):
    """Blueprint for the forward object."""

    # pylint: disable=too-few-public-methods
    con_name: str = ""
    use_this: bool = True
    source: Union[int, str] = ""
    dest: List[Union[int, str]] = []
    offset: int = 0
    end: Optional[int] = 0


class LiveSettings(BaseModel):
    """Settings to configure how tgcf operates in live mode."""

    # pylint: disable=too-few-public-methods
    sequential_updates: bool = False
    delete_sync: bool = False
    delete_on_edit: Optional[str] = ".deleteMe"
    album_flush_timeout: float = 0.6  # Seconds to wait after last album message before forwarding


class PastSettings(BaseModel):
    """Configuration for past mode."""

    # pylint: disable=too-few-public-methods
    delay: int = 0

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, val: int) -> int:  # pylint: disable=no-self-use,no-self-argument
        """Check if the delay used by user is valid. If not, use closest logical values."""
        if val not in range(0, 11):
            logging.warning("delay must be within 0 to 10 seconds")
            if val > 10:
                val = 10
            if val < 0:
                val = 0
        return val


class LoginConfig(BaseModel):

    API_ID: int = 0
    API_HASH: str = ""
    user_type: int = 0  # 0:bot, 1:user
    phone_no: int = 91
    USERNAME: str = ""
    SESSION_STRING: str = ""
    BOT_TOKEN: str = ""


class BotMessages(BaseModel):
    start: str = "Hi! I am alive"
    bot_help: str = "For details visit github.com/aahnik/tgcf"


class Config(BaseModel):
    """The blueprint for tgcf's whole config."""

    # pylint: disable=too-few-public-
    pid: int = 0
    theme: str = "light"
    login: LoginConfig = LoginConfig()
    admins: List[Union[int, str]] = []
    forwards: List[Forward] = []
    show_forwarded_from: bool = False # Show 'Forwarded from' in forwarded messages
    reply_chain: bool = False  # Forward reply chains from source to destination
    mode: int = 0  # 0: live, 1:past
    live: LiveSettings = LiveSettings()
    past: PastSettings = PastSettings()

    plugins: PluginConfig = PluginConfig()
    bot_messages: BotMessages = BotMessages()


def write_config_to_file(config: Config):
    """Write config atomically to prevent corruption on crash."""
    data = config.model_dump_json()

    dir_name = os.path.dirname(CONFIG_FILE_NAME) or "."
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf8",
        dir=dir_name,
        delete=False,
        suffix=".tmp"
    ) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())

    os.replace(tmp.name, CONFIG_FILE_NAME)


def detect_config_type() -> int:
    if os.getenv("MONGO_CON_STR"):
        if MONGO_CON_STR:
            logging.info("Using mongo db for storing config!")
            client = MongoClient(MONGO_CON_STR)
            stg.mycol = setup_mongo(client)
        return 2
    if CONFIG_FILE_NAME in os.listdir():
        logging.info(f"{CONFIG_FILE_NAME} detected!")
        return 1

    else:
        logging.info(
            "config file not found. mongo not found. creating local config file."
        )
        cfg = Config()
        write_config_to_file(cfg)
        logging.info(f"{CONFIG_FILE_NAME} created!")
        return 1


def read_config() -> Config:
    """Load the configuration defined by user."""
    if stg.CONFIG_TYPE == 1:
        try:
            with open(CONFIG_FILE_NAME, encoding="utf8") as file:
                return Config.model_validate_json(file.read())
        except FileNotFoundError:
            logging.warning(f"{CONFIG_FILE_NAME} not found, using default config")
            return Config()
        except Exception as err:
            logging.error(f"Failed to parse {CONFIG_FILE_NAME}: {err}")
            raise
    elif stg.CONFIG_TYPE == 2:
        return read_db()
    else:
        return Config()


def write_config(config: Config):
    """Write changes in config back to file."""
    if stg.CONFIG_TYPE == 1 or stg.CONFIG_TYPE == 0:
        write_config_to_file(config)
    elif stg.CONFIG_TYPE == 2:
        update_db(config)


# TODO: replace with telethon's get_peer_id when that gets fixed
async def get_id(client: TelegramClient, peer):
    """Get the ID of a peer (can be username, phone, or ID)"""
    try:
        # peer is already an integer ID
        if isinstance(peer, int):
            return peer
        # peer is an integer string, convert it
        if isinstance(peer, str) and peer.lstrip('-').isdigit():
            return int(peer)
        # get the entity first, then extract ID
        entity = await client.get_entity(peer)
        return entity.id
    except Exception as err:
        logging.error(f"Failed to get ID for peer {peer}: {err}")
        raise


async def load_from_to(
    client: TelegramClient, forwards: List[Forward]
) -> Dict[int, List[int]]:
    """Convert a list of Forward objects to a mapping.

    Args:
        client: Instance of Telegram client (logged in)
        forwards: List of Forward objects

    Returns:
        Dict: key = chat id of source
                value = List of chat ids of destinations

    Notes:
    -> The Forward objects may contain username/phn no/links
    -> But this mapping strictly contains signed integer chat ids
    -> Chat ids are essential for how storage is implemented
    -> Storage is essential for edit, delete and reply syncs
    """
    from_to_dict = {}

    async def _(peer):
        return await get_id(client, peer)

    for forward in forwards:
        if not forward.use_this:
            continue
        source = forward.source
        if not isinstance(source, int) and source.strip() == "":
            continue
        src = await _(forward.source)
        from_to_dict[src] = [await _(dest) for dest in forward.dest]
    logging.info(f"From to dict is {from_to_dict}")
    return from_to_dict


async def load_admins(client: TelegramClient):
    for admin in CONFIG.admins:
        ADMINS.append(await get_id(client, admin))
    logging.info(f"Loaded admins are {ADMINS}")
    return ADMINS


def setup_mongo(client):

    mydb = client[MONGO_DB_NAME]
    mycol = mydb[MONGO_COL_NAME]
    if not mycol.find_one({"_id": 0}):
        mycol.insert_one({"_id": 0, "author": "tgcf", "config": Config().model_dump()})

    return mycol


def update_db(cfg):
    stg.mycol.update_one({"_id": 0}, {"$set": {"config": cfg.model_dump()}})


def read_db():
    obj = stg.mycol.find_one({"_id": 0})
    cfg = Config(**obj["config"])
    return cfg


PASSWORD = os.getenv("PASSWORD", "tgcf")
ADMINS = []

MONGO_CON_STR = os.getenv("MONGO_CON_STR")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "tgcf-config")
MONGO_COL_NAME = os.getenv("MONGO_COL_NAME", "tgcf-instance-0")

stg.CONFIG_TYPE = detect_config_type()
CONFIG = read_config()

if PASSWORD == "tgcf":
    logging.warning(
        "You have not set a password to protect the web access to tgcf.\nThe default password `tgcf` is used."
    )
from_to = {}
is_bot: Optional[bool] = None
logging.info("config.py got executed")


def get_SESSION(section: Any = CONFIG.login, default: str = 'tgcf_bot'):
    if section.SESSION_STRING and section.user_type == 1:
        logging.info("using session string")
        return StringSession(section.SESSION_STRING)
    elif section.BOT_TOKEN and section.user_type == 0:
        logging.info("using bot account")
        return default

    raise ConfigurationError(
        "Login information not set!"
        "Set either SESSION_STRING or BOT_TOKEN in config file or environment variables."
    )