"""A bot to control settings for tgcf live mode."""

import logging

import yaml
from telethon import events

from tgcf.bot.utils import (
    make_admin_protect,
    display_forwards,
    get_args,
    get_command_prefix,
    remove_source,
)
from tgcf.config import Forward, load_from_to, write_config
from tgcf.context import TgcfContext
from tgcf.plugin_models import Style


def make_forward_command_handler(ctx: TgcfContext):
    """Factory to create forward command handler with context closure."""
    admin_protect = make_admin_protect(ctx)

    @admin_protect
    async def handler(event):
        """Handle the `/forward` command."""
        notes = """The `/forward` command allows you to add a new forward.
        Example: suppose you want to forward from a to (b and c)

        ```
        /forward source: a
        dest: [b,c]
        ```

        a,b,c are chat ids

        """.replace(
            "    ", ""
        )

        try:
            args = get_args(event.message.text)
            if not args:
                raise ValueError(f"{notes}\n{display_forwards(ctx.config.forwards)}")

            parsed_args = yaml.safe_load(args)
            forward = Forward(**parsed_args)
            try:
                remove_source(forward.source, ctx.config.forwards)
            except Exception as err:
                logging.error(err)
            ctx.config.forwards.append(forward)
            ctx.from_to = await load_from_to(ctx.client, ctx.config.forwards)

            await event.respond("Success")
            write_config(ctx.config)
        except ValueError as err:
            logging.error(err)
            await event.respond(str(err))

        finally:
            raise events.StopPropagation

    return handler


def make_remove_command_handler(ctx: TgcfContext):
    """Factory to create remove command handler with context closure."""
    admin_protect = make_admin_protect(ctx)

    @admin_protect
    async def handler(event):
        """Handle the /remove command."""
        notes = """The `/remove` command allows you to remove a source from forwarding.
        Example: Suppose you want to remove the channel with id -100, then run

        `/remove source: -100`

        """.replace(
            "    ", ""
        )

        try:
            args = get_args(event.message.text)
            if not args:
                raise ValueError(f"{notes}\n{display_forwards(ctx.config.forwards)}")

            parsed_args = yaml.safe_load(args)
            source_to_remove = parsed_args.get("source")
            ctx.config.forwards = remove_source(source_to_remove, ctx.config.forwards)
            ctx.from_to = await load_from_to(ctx.client, ctx.config.forwards)

            await event.respond("Success")
            write_config(ctx.config)
        except ValueError as err:
            logging.error(err)
            await event.respond(str(err))

        finally:
            raise events.StopPropagation

    return handler


def make_style_command_handler(ctx: TgcfContext):
    """Factory to create style command handler with context closure."""
    admin_protect = make_admin_protect(ctx)

    @admin_protect
    async def handler(event):
        """Handle the /style command"""
        notes = """This command is used to set the style of the messages to be forwarded.

        Example: `/style bold`

        Options are preserve,normal,bold,italics,code, strike

        """.replace(
            "    ", ""
        )

        try:
            args = get_args(event.message.text)
            if not args:
                raise ValueError(f"{notes}\n")
            _valid = [item.value for item in Style]
            if args not in _valid:
                raise ValueError(f"Invalid style. Choose from {_valid}")
            ctx.config.plugins.fmt.style = args
            await event.respond("Success")
            write_config(ctx.config)
        except ValueError as err:
            logging.error(err)
            await event.respond(str(err))

        finally:
            raise events.StopPropagation

    return handler


def make_start_command_handler(ctx: TgcfContext):
    """Factory to create start command handler with context closure."""

    async def handler(event):
        """Handle the /start command."""
        await event.respond(ctx.config.bot_messages.start)

    return handler


def make_help_command_handler(ctx: TgcfContext):
    """Factory to create help command handler with context closure."""

    async def handler(event):
        """Handle the /help command."""
        await event.respond(ctx.config.bot_messages.bot_help)

    return handler


def get_events(ctx: TgcfContext) -> dict:
    """Get command event handlers with context bound via closures.
    
    Args:
        ctx: TgcfContext with is_bot set (for command prefix)
    
    Returns:
        Dict mapping command names to (handler, event) tuples
    """
    prefix = get_command_prefix(ctx)
    logging.info("Command prefix is . for userbot and / for bot")
    
    command_events = {
        "start": (make_start_command_handler(ctx), events.NewMessage(pattern=f"{prefix}start")),
        "forward": (make_forward_command_handler(ctx), events.NewMessage(pattern=f"{prefix}forward")),
        "remove": (make_remove_command_handler(ctx), events.NewMessage(pattern=f"{prefix}remove")),
        "style": (make_style_command_handler(ctx), events.NewMessage(pattern=f"{prefix}style")),
        "help": (make_help_command_handler(ctx), events.NewMessage(pattern=f"{prefix}help")),
    }

    return command_events
