"""List all channels/groups the user has joined and save to file."""

import logging
from telethon.errors import AuthKeyError
import asyncio
from pathlib import Path
from telethon import TelegramClient
from tgcf.config import CONFIG, get_SESSION


async def list_channels() -> None:
    """List all channels and groups with their IDs, saving results to a file."""
    SESSION = get_SESSION()
    DEFAULT_OUTPUT_FILE = Path("channels.txt")

    stats = {"channels": 0, "supergroups": 0, "groups": 0, "protected": 0}

    try:
        async with TelegramClient(
            SESSION, CONFIG.login.API_ID, CONFIG.login.API_HASH
        ) as client:
            separator = "=" * 60
            header = f"{separator}\nCHANNELS & GROUPS YOU'VE JOINED\n{separator}\n\n"
            print(header)

            lines = [header]

            async for dialog in client.iter_dialogs():
                # Filter for channels, groups, and megagroups
                if dialog.is_channel or dialog.is_group:
                    entity = dialog.entity

                    if getattr(entity, 'megagroup', False):
                        chat_type = "Supergroup"
                        stats["supergroups"] += 1
                    elif getattr(entity, 'broadcast', False):
                        chat_type = "Channel"
                        stats["channels"] += 1
                    else:
                        chat_type = "Group"
                        stats["groups"] += 1

                    # Check if restricted/protected
                    restricted = ""
                    if getattr(entity, 'noforwards', False):
                        restricted = " [PROTECTED]"
                        stats["protected"] += 1

                    entry = f"[{chat_type}]{restricted}\n"
                    entry += f"\tName: {dialog.name}\n"
                    entry += f"\tID: {dialog.id}\n"
                    if getattr(entity, 'username', None):
                        entry += f"\tUsername: @{entity.username}\n"
                    entry += "\n"

                    print(entry, end="")
                    lines.append(entry)

            # Summary
            total = stats["channels"] + stats["supergroups"] + stats["groups"]
            separator = "=" * 60
            summary = (
                f"{separator}\n"
                "SUMMARY\n"
                f"{separator}\n"
                f"  Total: {total}\n"
                f"  Channels: {stats['channels']}\n"
                f"  Supergroups: {stats['supergroups']}\n"
                f"  Groups: {stats['groups']}\n"
                f"  Protected (noforwards): {stats['protected']}\n"
                f"{separator}\n"
            )
            print(summary)
            lines.append(summary)

            # Write to file
            DEFAULT_OUTPUT_FILE.write_text("".join(lines), encoding="utf-8")

            success_msg = f"\nResults saved to: {DEFAULT_OUTPUT_FILE.absolute()}\n"
            print(success_msg)
    except (ConnectionError, AuthKeyError) as e:
        logging.error(f"\nTelegram connection error: {e}")
        raise
    except Exception as e:
        logging.error(f"\nUnexpected error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(list_channels())
