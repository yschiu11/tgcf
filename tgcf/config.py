"""Load all user defined config and env vars."""

import logging
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator  # pylint: disable=no-name-in-module
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.utils import get_peer_id

from tgcf.const import CONFIG_FILE_NAME
from tgcf.plugin_models import PluginConfig


class ConfigurationError(Exception):
    """Raised when configuration is invalid or incomplete."""
    pass


class Forward(BaseModel):
    """Blueprint for the forward object."""

    # pylint: disable=too-few-public-methods
    model_config = ConfigDict(populate_by_name=True)

    config_name: str = Field("", alias="con_name")
    enabled: bool = Field(True, alias="use_this")
    source: int | str = ""
    dest: list[int | str] = []
    offset: int = 0
    end: int | None = 0


class LiveSettings(BaseModel):
    """Settings to configure how tgcf operates in live mode."""

    # pylint: disable=too-few-public-methods
    sequential_updates: bool = False
    delete_sync: bool = False
    delete_on_edit: str | None = ".deleteMe"
    album_flush_timeout: float = 0.6  # Seconds to wait after last album message before forwarding


class PastSettings(BaseModel):
    """Configuration for past mode."""

    # pylint: disable=too-few-public-methods
    delay: int = 0

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, val: int) -> int:  # pylint: disable=no-self-use,no-self-argument
        if not 0 <= val <= 10:
            raise ValueError(f"Delay must be between 0 and 10 seconds, got {val}")
        return val


class LoginConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    api_id: int = Field(0, alias="API_ID")
    api_hash: str = Field("", alias="API_HASH")
    user_type: int = 0  # 0:bot, 1:user
    phone_no: int = 91
    username: str = Field("", alias="USERNAME")
    session_string: str = Field("", alias="SESSION_STRING")
    bot_token: str = Field("", alias="BOT_TOKEN")


class BotMessages(BaseModel):
    start: str = "Hi! I am alive"
    bot_help: str = "For details visit github.com/aahnik/tgcf"


class Config(BaseModel):
    """The blueprint for tgcf's whole config."""
    model_config = ConfigDict(populate_by_name=True)

    # pylint: disable=too-few-public-
    process_id: int = Field(0, alias="pid")
    theme: str = "light"
    login: LoginConfig = LoginConfig()
    admins: list[int | str] = []
    forwards: list[Forward] = []
    show_forwarded_from: bool = False # Show 'Forwarded from' in forwarded messages
    reply_chain: bool = False  # Forward reply chains from source to destination
    mode: int = 0  # 0: live, 1:past
    live: LiveSettings = LiveSettings()
    past: PastSettings = PastSettings()

    plugins: PluginConfig = PluginConfig()
    bot_messages: BotMessages = BotMessages()


def write_config(config: Config, path: str = CONFIG_FILE_NAME) -> None:
    """Write config atomically to prevent corruption on crash.
    
    Args:
        config: Config object to serialize
        path: File path to write to (defaults to CONFIG_FILE_NAME)
    """
    data = config.model_dump_json()

    dir_name = Path(path).parent
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

    os.replace(tmp.name, path)


def ensure_config_exists(path: str = CONFIG_FILE_NAME) -> None:
    """Create default config file if it doesn't exist.

    Args:
        path: File path to check/create (defaults to CONFIG_FILE_NAME)
    """
    if Path(path).exists():
        logging.info(f"{path} detected!")
        return

    logging.info(f"Config file not found. Creating default config at {path}.")
    cfg = Config()
    write_config(cfg, path)
    logging.info(f"{path} created!")


def read_config(path: str = CONFIG_FILE_NAME) -> Config:
    """Load the configuration from file.

    Args:
        path: File path to read from (defaults to CONFIG_FILE_NAME)
    """
    try:
        with open(path, encoding="utf8") as file:
            return Config.model_validate_json(file.read())
    except FileNotFoundError:
        logging.warning(f"{path} not found, using default config")
        return Config()
    except Exception as err:
        logging.error(f"Failed to parse {path}: {err}")
        raise


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
        return get_peer_id(entity)
    except Exception as err:
        logging.error(f"Failed to get ID for peer {peer}: {err}")
        raise


async def resolve_forward_rules(
    client: TelegramClient, forwards: list[Forward]
) -> dict[int, tuple[Forward, list[int]]]:
    """Convert Forward objects to a mapping with resolved IDs.

    Args:
        client: Instance of Telegram client (logged in)
        forwards: List of Forward objects

    Returns:
        Dict mapping src_chat -> (original Forward, resolved dest_chats)

    Notes:
    -> The Forward objects may contain username/phn no/links
    -> But this mapping strictly contains signed integer chat ids
    -> The Forward reference is preserved for offset tracking in past mode
    """
    from_to_dict: dict[int, tuple[Forward, list[int]]] = {}

    async def resolve_id(peer):
        return await get_id(client, peer)

    for forward in forwards:
        if not forward.enabled:
            continue
        raw_src = forward.source
        if not isinstance(raw_src, int) and raw_src.strip() == "":
            continue
        src_chat = await resolve_id(raw_src)
        dest_chats = [await resolve_id(raw_dest) for raw_dest in forward.dest]
        from_to_dict[src_chat] = (forward, dest_chats)
    logging.info(f"Loaded {len(from_to_dict)} active forwards")
    return from_to_dict


async def load_admins(client: TelegramClient, admins: list[int | str]) -> list[int]:
    """Resolve admin usernames/IDs to integer IDs."""
    resolved = [await get_id(client, admin) for admin in admins]
    logging.info(f"Loaded admins are {resolved}")
    return resolved


def get_session(login: LoginConfig, default: str = 'tgcf_bot'):
    """Get session for Telegram client.
    
    Args:
        login: LoginConfig section from config
        default: Default session name for bot accounts
    """
    if login.session_string and login.user_type == 1:
        logging.info("using session string")
        return StringSession(login.session_string)
    elif login.bot_token and login.user_type == 0:
        logging.info("using bot account")
        return default

    raise ConfigurationError(
        "Login information not set! "
        "Set either SESSION_STRING or BOT_TOKEN in config file or environment variables."
    )