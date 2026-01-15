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
# TODO: ignore because dependency issue on pydantic v2
# from verlat import latest_release

from tgcf import __version__

load_dotenv(".env")

FAKE = bool(os.getenv("FAKE"))
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
    if FAKE:
        logging.critical(f"You are running fake with {mode} mode")
        sys.exit(1)

    if mode == Mode.PAST:
        from tgcf.past import forward_job  # pylint: disable=import-outside-toplevel

        asyncio.run(forward_job())
    else:
        from tgcf.live import start_sync  # pylint: disable=import-outside-toplevel

        asyncio.run(start_sync())


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
    if FAKE:
        logging.critical("You are running fake with link mode")
        sys.exit(1)

    from tgcf.link import forward_link_job  # pylint: disable=import-outside-toplevel

    asyncio.run(forward_link_job(url, dest))


# AAHNIK 2021
