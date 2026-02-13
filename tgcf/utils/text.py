"""Regex matching, text replacement, and Telegram link parsing."""

import re

from tgcf.plugin_models import STYLE_CODES


def match(pattern: str, string: str, regex: bool) -> bool:
    """Check if pattern matches string.

    Args:
        pattern: The pattern to search for.
        string: The string to search in.
        regex: If True, treat pattern as a regex.
    """
    if regex:
        return bool(re.findall(pattern, string))
    return pattern in string


def replace(pattern: str, new: str, string: str, regex: bool) -> str:
    """Replace pattern in string, with optional regex and style support.

    Args:
        pattern: The pattern to find.
        new: The replacement string (or a style code key).
        string: The source string.
        regex: If True, treat pattern as a regex.
    """

    def fmt_repl(matched: re.Match[str]) -> str:
        style = new
        s = STYLE_CODES.get(style)
        return f"{s}{matched.group(0)}{s}"

    if regex:
        if new in STYLE_CODES:
            return re.sub(pattern, fmt_repl, string)
        return re.sub(pattern, new, string)
    else:
        return string.replace(pattern, new)


def parse_telegram_link(url: str) -> tuple[str | int, int] | None:
    """Parse a Telegram post link into (channel, message_id).

    Supports:
    - Public: https://t.me/channel_username/123
    - Private: https://t.me/c/1234567890/123

    Returns:
        Tuple of (channel_identifier, message_id) or None if invalid.
    """
    # TODO: Confirm link formats
    patterns = [
        # Public: https://t.me/channel_name/123 or t.me/channel_name/123
        (r"(?:https?://)?t\.me/([a-zA-Z_][a-zA-Z0-9_]{3,})/(\d+)", False),
        # Private: https://t.me/c/1234567890/123
        (r"(?:https?://)?t\.me/c/(\d+)/(\d+)", True),
    ]

    for pattern, is_private in patterns:
        m = re.match(pattern, url)
        if m:
            channel: str | int = m.group(1)
            msg_id = int(m.group(2))
            # For private links, convert to proper channel ID format
            if is_private:
                channel = int(f"-100{channel}")
            return (channel, msg_id)
    return None
