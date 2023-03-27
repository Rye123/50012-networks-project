from datetime import datetime, timezone
from pathlib import Path

def get_current_timestamp() -> float:
    """
    Returns the current UTC time as a POSIX timestamp.
    """
    return datetime.now(timezone.utc).timestamp()


