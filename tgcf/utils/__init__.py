"""Utility subpackage for tgcf.

This package organises utility functions by responsibility:

- ``buffer``: Album buffering and grouped-message detection.
- ``io``: Filesystem helpers (cleanup, stamping, safe names).
- ``text``: Regex matching, text replacement, Telegram link parsing.
- ``sender``: Telegram message sending, forwarding, and fallback logic.

For backward compatibility every public symbol is re-exported here so that
existing ``from tgcf.utils import X`` statements continue to work.
"""


from tgcf.utils.buffer import (
    ALBUM_SEARCH_RADIUS,
    AlbumBuffer,
    fetch_album_by_message,
)
from tgcf.utils.io import (
    cleanup,
    platform_info,
    safe_name,
    stamp,
)
from tgcf.utils.sender import (
    forward_album,
    forward_album_anonymous,
    forward_by_link,
    forward_single_message,
    get_reply_to_mapping,
    resolve_dest_ids,
    send_album,
    send_album_with_fallback,
    send_message,
    send_single_message_with_fallback,
)
from tgcf.utils.text import (
    match,
    parse_telegram_link,
    replace,
)
