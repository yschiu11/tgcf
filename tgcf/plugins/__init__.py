"""Subpackage of tgcf: plugins.

Contains all the first-party tgcf plugins.
"""


import inspect
import logging
from enum import Enum
from importlib import import_module
from typing import Any, Dict

from telethon.tl.custom.message import Message

from tgcf.config import Config
from tgcf.plugin_models import FileType, ASYNC_PLUGIN_IDS, PluginConfig
from tgcf.utils import cleanup, stamp


class TgcfMessage:
    def __init__(self, message: Message) -> None:
        self.message = message
        self.text = self.message.text
        self.raw_text = self.message.raw_text
        self.sender_id = self.message.sender_id
        self.file_type = self.guess_file_type()
        self.new_file = None
        self.cleanup = False
        self.reply_to = None
        self.client = self.message.client

    async def get_file(self) -> str:
        """Downloads the file in the message and returns the path where its saved."""
        if self.file_type == FileType.NOFILE:
            raise FileNotFoundError("No file exists in this message.")
        self.file = stamp(await self.message.download_media(""), self.sender_id)
        return self.file

    def guess_file_type(self) -> FileType:
        for i in FileType:
            if i == FileType.NOFILE:
                return i
            obj = getattr(self.message, i.value)
            if obj:
                return i

    def clear(self) -> None:
        if self.new_file and self.cleanup:
            cleanup(self.new_file)
            self.new_file = None


class TgcfPlugin:
    id_ = "plugin"

    def __init__(self, data: Dict[str, Any]) -> None:  # TODO data type has changed
        self.data = data

    async def __ainit__(self) -> None:
        """Asynchronous initialization here."""

    def modify(self, tm: TgcfMessage) -> TgcfMessage | None:
        """Modify the message here."""
        return tm


def load_plugins(plugin_config: PluginConfig) -> dict[str, TgcfPlugin]:
    """Load the plugins specified in config.
    
    Args:
        plugin_config: PluginConfig from Config object
    """
    _plugins = {}
    for item in plugin_config:
        plugin_id = item[0]
        if item[1].check == False:
            continue

        plugin_class_name = f"Tgcf{plugin_id.title()}"

        try:  # try to load first party plugin
            plugin_module = import_module("tgcf.plugins." + plugin_id)
        except ModuleNotFoundError:
            logging.error(
                f"{plugin_id} is not a first party plugin. Third party plugins are not supported."
            )
        else:
            logging.info(f"First party plugin {plugin_id} loaded!")

        try:
            plugin_class = getattr(plugin_module, plugin_class_name)
            if not issubclass(plugin_class, TgcfPlugin):
                logging.error(
                    f"Plugin class {plugin_class_name} does not inherit TgcfPlugin"
                )
                continue
            plugin: TgcfPlugin = plugin_class(item[1])
            if not plugin.id_ == plugin_id:
                logging.error(f"Plugin id for {plugin_id} does not match expected id.")
                continue
        except AttributeError:
            logging.error(f"Found plugin {plugin_id}, but plugin class not found.")
        else:
            logging.info(f"Loaded plugin {plugin_id}")
            _plugins.update({plugin.id_: plugin})
    return _plugins


# Module-level plugins cache - initialized lazily
_plugins: dict[str, TgcfPlugin] | None = None


def get_plugins(plugin_config: PluginConfig) -> dict[str, TgcfPlugin]:
    """Get or initialize plugins from config.
    
    Plugins are loaded once and cached for the lifetime of the process.
    """
    global _plugins
    if _plugins is None:
        _plugins = load_plugins(plugin_config)
    return _plugins


async def load_async_plugins(plugin_config: PluginConfig) -> None:
    """Load async plugins specified in plugin_models.
    
    Args:
        plugin_config: PluginConfig from Config object
    """
    plugins = get_plugins(plugin_config)
    if plugins:
        for id in ASYNC_PLUGIN_IDS:
            if id in plugins:
                await plugins[id].__ainit__()
                logging.info(f"Plugin {id} asynchronously loaded")


async def apply_plugins(message: Message, plugin_config: PluginConfig) -> TgcfMessage | None:
    """Apply all loaded plugins to a message.

    Return None if message should be dropped (filtered or plugin failure).
    
    Args:
        message: The Telethon message object
        plugin_config: PluginConfig from Config object
    """
    tm = TgcfMessage(message)
    plugins = get_plugins(plugin_config)

    for _id, plugin in plugins.items():
        try:
            if inspect.iscoroutinefunction(plugin.modify):
                new_tm = await plugin.modify(tm)
            else:
                new_tm = plugin.modify(tm)

            # plugin filters the message
            if new_tm is None:
                logging.info(f"Message filtered by plugin {_id}")
                tm.clear()
                return None

            tm = new_tm
            logging.info(f"Applied plugin {_id}")

        except Exception as err:
            logging.error(f"Plugin {_id} failed: {err}. Skipping this plugin.")

    return tm
