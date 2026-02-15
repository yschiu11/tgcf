"""This module implements the command line interface for tgcf."""

import asyncio
import logging
import os
import sys
from enum import Enum

import typer
from dotenv import load_dotenv
from rich import traceback
from rich.console import Console
from rich.logging import RichHandler
from telethon import TelegramClient
from telethon.sessions import StringSession

from tgcf import __version__
from tgcf.config import (
    ensure_config_exists,
    get_SESSION,
    load_admins,
    load_from_to,
    read_config,
)
from tgcf.const import CONFIG_ENV_VAR_NAME, CONFIG_FILE_NAME
from tgcf.context import TgcfContext
from tgcf.link import forward_link_job
from tgcf.live import start_sync
from tgcf.past import forward_job
from tgcf.plugins import load_async_plugins

app = typer.Typer(add_completion=False)
console = Console()


def _load_env_and_config_path() -> str:
    """Load .env from CWD and return the resolved config file path."""
    env_path = os.path.join(os.getcwd(), ".env")
    load_dotenv(env_path)
    return os.getenv(CONFIG_ENV_VAR_NAME, CONFIG_FILE_NAME)


class Mode(str, Enum):
    """tgcf works in two modes."""

    PAST = "past"
    LIVE = "live"


def configure_logging(value: bool | None):
    """Set logging level."""
    traceback.install()
    if value:
        level = logging.INFO
        logging.info("Verbosity turned on! This is suitable for debugging")
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


def version_callback(value: bool | None):
    """Show current version and exit."""

    if value:
        console.print(__version__)
        raise typer.Exit()


async def _run_past_mode(ctx: TgcfContext, session: str | StringSession) -> None:
    """Run tgcf in past mode to forward historical messages.

    Args:
        ctx: Initialized context with config and config_path.
        session: Telegram session string or bot session name.

    Raises:
        SystemExit: If a bot account is configured (bots cannot access history).
    """
    if ctx.config.login.user_type != 1:
        logging.critical(
            "You cannot use bot account for tgcf past mode. "
            "Telegram does not allow bots to access chat history."
        )
        sys.exit(1)

    async with TelegramClient(
        session, ctx.config.login.API_ID, ctx.config.login.API_HASH
    ) as client:
        ctx.bind_client(client)
        ctx.from_to = await load_from_to(client, ctx.config.forwards)
        await forward_job(ctx)


async def _run_live_mode(ctx: TgcfContext, session: str | StringSession) -> None:
    """Run tgcf in live mode for real-time message forwarding.

    Args:
        ctx: Initialized context with config and config_path.
        session: Telegram session string or bot session name.

    Raises:
        SystemExit: If bot token is missing when user_type is bot.
    """
    client = TelegramClient(
        session,
        ctx.config.login.API_ID,
        ctx.config.login.API_HASH,
        sequential_updates=ctx.config.live.sequential_updates,
    )
    ctx.bind_client(client)

    if ctx.config.login.user_type == 0:
        if not ctx.config.login.BOT_TOKEN:
            logging.critical("Bot token not found, but login type is set to bot.")
            sys.exit(1)
        await ctx.client.start(bot_token=ctx.config.login.BOT_TOKEN)
    else:
        await ctx.client.start()

    ctx.is_bot = await ctx.client.is_bot()
    ctx.admins = await load_admins(ctx.client, ctx.config.admins)
    ctx.from_to = await load_from_to(ctx.client, ctx.config.forwards)

    await start_sync(ctx)


async def run_forwarding_mode(mode: Mode, config_path: str) -> None:
    """Build context with client and run the appropriate mode."""
    ensure_config_exists(config_path)
    config = read_config(config_path)
    await load_async_plugins(config.plugins)

    ctx = TgcfContext(config=config, config_path=config_path)
    session = get_SESSION(config.login)

    if mode == Mode.PAST:
        await _run_past_mode(ctx, session)
    else:
        await _run_live_mode(ctx, session)


@app.command()
def main(
    mode: Mode = typer.Argument(
        ..., help="Choose the mode in which you want to run tgcf.", envvar="TGCF_MODE"
    ),
    verbose: bool | None = typer.Option(  # pylint: disable=unused-argument
        None,
        "--loud",
        "-l",
        callback=configure_logging,
        envvar="LOUD",
        help="Increase output verbosity.",
    ),
    version: bool | None = typer.Option(  # pylint: disable=unused-argument
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
    config_path = _load_env_and_config_path()

    asyncio.run(run_forwarding_mode(mode, config_path))


@app.command()
def link(
    url: str = typer.Argument(..., help="Telegram post link (e.g., https://t.me/channel/123)"),
    dest: list[str] = typer.Option(
        ..., "--dest", "-d", help="Destination chat ID or username (can specify multiple)"
    ),
    verbose: bool | None = typer.Option(
        None,
        "--loud",
        "-l",
        callback=configure_logging,
        help="Increase output verbosity.",
    ),
):
    """Forward a single message or album by its Telegram post link.

    Sends as a clean copy without 'Forwarded from' attribution.

    Example usage:

        tgcf link "https://t.me/durov/123" -d @my_channel

        tgcf link "https://t.me/c/1234567890/456" -d -100123456 -d @backup_channel
    """
    config_path = _load_env_and_config_path()

    asyncio.run(forward_link_job(url, dest, config_path))
