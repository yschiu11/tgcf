"""Filesystem helpers: cleanup, file stamping, safe naming, platform info."""

import logging
import os
import platform
import re
import sys
from datetime import datetime



def platform_info() -> str:
    """Return a multi-line string describing the runtime environment."""
    nl = "\n"
    return f"""Running tgcf\
    \nPython {sys.version.replace(nl, "")}\
    \nOS {os.name}\
    \nPlatform {platform.system()} {platform.release()}\
    \n{platform.architecture()} {platform.processor()}"""


def cleanup(*files: str) -> None:
    """Delete files by path, logging if any do not exist.

    Args:
        *files: Paths to delete.
    """
    for file in files:
        try:
            os.remove(file)
        except FileNotFoundError:
            logging.info(f"File {file} does not exist, so cannot delete it.")


def stamp(file: str, user: str) -> str:
    """Rename a file by prepending user info and a timestamp.

    Args:
        file: Original file path.
        user: Identifier to include in the new name.

    Returns:
        The new file path, or the original path if renaming fails.
    """
    now = str(datetime.now())
    outf = safe_name(f"{user} {now} {file}")
    try:
        os.rename(file, outf)
        return outf
    except Exception as err:
        logging.warning(f"Stamping file name failed for {file} to {outf}. \n {err}")
        return file


def safe_name(string: str) -> str:
    """Replace special characters with underscores to produce a safe filename.

    Args:
        string: Raw filename string.
    """
    return re.sub(pattern=r"[-!@#$%^&*()\s]", repl="_", string=string)
