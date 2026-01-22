"""This module implements the command line interface for tgcf."""

import asyncio
import logging
import os
import sys
from enum import Enum
from typing import Optional

import typer
from dotenv import load_dotenv
from rich import console, traceback
from rich.logging import RichHandler
from telethon import TelegramClient

from tgcf import __version__
from tgcf.const import CONFIG_FILE_NAME
from tgcf.config import (
    ensure_config_exists,
    read_config,
    get_SESSION,
    load_from_to,
    load_admins,
)
from tgcf.context import TgcfContext
from tgcf.plugins import load_async_plugins

app = typer.Typer(add_completion=False)

con = console.Console()


def topper():
    print("tgcf")
    version_check()
    print("\n")


class Mode(str, Enum):
    """tgcf works in two modes."""

    PAST = "past"
    LIVE = "live"


def verbosity_callback(value: bool):
    """Set logging level."""
    traceback.install()
    if value:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                markup=True,
            )
        ],
    )
    topper()
    logging.info("Verbosity turned on! This is suitable for debugging")


def version_callback(value: bool):
    """Show current version and exit."""

    if value:
        con.print(__version__)
        raise typer.Exit()


def version_check():
    """Deprecated: This function is no longer used due to dependency issues."""
    pass


async def _run(mode: Mode, config_path: str) -> None:
    """Build context with client and run the appropriate mode."""
    from tgcf.past import forward_job  # pylint: disable=import-outside-toplevel
    from tgcf.live import start_sync  # pylint: disable=import-outside-toplevel

    ensure_config_exists(config_path)
    config = read_config(config_path)
    await load_async_plugins(config.plugins)
    ctx = TgcfContext(config=config, config_path=config_path)

    if mode == Mode.PAST:
        if config.login.user_type != 1:
            logging.warning(
                "You cannot use bot account for tgcf past mode. "
                "Telegram does not allow bots to access chat history."
            )
            return

        session = get_SESSION(config.login)
        async with TelegramClient(
            session, config.login.API_ID, config.login.API_HASH
        ) as client:
            ctx.client = client
            ctx.from_to = await load_from_to(client, config.forwards)
            await forward_job(ctx)
    else:
        session = get_SESSION(config.login)
        ctx.client = TelegramClient(
            session,
            config.login.API_ID,
            config.login.API_HASH,
            sequential_updates=config.live.sequential_updates,
        )

        if config.login.user_type == 0:
            if config.login.BOT_TOKEN == "":
                logging.warning("Bot token not found, but login type is set to bot.")
                sys.exit()
            await ctx.client.start(bot_token=config.login.BOT_TOKEN)
        else:
            await ctx.client.start()

        ctx.is_bot = await ctx.client.is_bot()
        ctx.admins = await load_admins(ctx.client, config.admins)
        ctx.from_to = await load_from_to(ctx.client, config.forwards)

        await start_sync(ctx)


@app.command()
def main(
    mode: Mode = typer.Argument(
        ..., help="Choose the mode in which you want to run tgcf.", envvar="TGCF_MODE"
    ),
    verbose: Optional[bool] = typer.Option(  # pylint: disable=unused-argument
        None,
        "--loud",
        "-l",
        callback=verbosity_callback,
        envvar="LOUD",
        help="Increase output verbosity.",
    ),
    version: Optional[bool] = typer.Option(  # pylint: disable=unused-argument
        None,
        "--version",
        "-v",
        callback=version_callback,
        help="Show version and exit.",
    ),
):
    """The ultimate tool to automate custom telegram message forwarding.

    Source Code: https://github.com/aahnik/tgcf

    For updates join telegram channel @aahniks_code

    To run web interface run `tgcf-web` command.
    """
    # Load environment from .env in current directory
    env_path = os.path.join(os.getcwd(), ".env")
    load_dotenv(env_path)

    if bool(os.getenv("FAKE")):
        logging.critical(f"You are running fake with {mode} mode")
        sys.exit(1)

    # Determine config path from env or use default
    config_path = os.getenv("TGCF_CONFIG", CONFIG_FILE_NAME)

    asyncio.run(_run(mode, config_path))


@app.command()
def link(
    url: str = typer.Argument(..., help="Telegram post link (e.g., https://t.me/channel/123)"),
    dest: list[str] = typer.Option(
        ..., "--dest", "-d", help="Destination chat ID or username (can specify multiple)"
    ),
    verbose: Optional[bool] = typer.Option(
        None,
        "--loud",
        "-l",
        callback=verbosity_callback,
        help="Increase output verbosity.",
    ),
):
    """Forward a single message or album by its Telegram post link.

    Sends as a clean copy without 'Forwarded from' attribution.

    Example usage:

        tgcf link "https://t.me/durov/123" -d @my_channel

        tgcf link "https://t.me/c/1234567890/456" -d -100123456 -d @backup_channel
    """
    # Load environment from .env in current directory
    env_path = os.path.join(os.getcwd(), ".env")
    load_dotenv(env_path)

    if bool(os.getenv("FAKE")):
        logging.critical("You are running fake with link mode")
        sys.exit(1)

    from tgcf.link import forward_link_job  # pylint: disable=import-outside-toplevel

    asyncio.run(forward_link_job(url, dest))


# AAHNIK 2021
