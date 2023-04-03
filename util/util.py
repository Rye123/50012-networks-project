"""
Provides various helper functions
"""

from datetime import datetime, timezone
from sys import stdout
from logging import StreamHandler, Formatter

def get_current_timestamp() -> float:
    """
    Returns the current UTC time as a POSIX timestamp.
    """
    return datetime.now(timezone.utc).timestamp()

standardHandler = StreamHandler(stdout)
standardHandler.setFormatter(fmt=Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s', '%H:%M:%S'))