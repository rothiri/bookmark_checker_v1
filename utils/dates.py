from __future__ import annotations

from datetime import datetime

def human_date_from_add_date(add_date: int) -> str:
    """
    Convert Chrome bookmark ADD_DATE (unix timestamp seconds) into YYYY-MM-DD.
    If missing/0, returns "unknown".
    """
    if not add_date:
        return "unknown"
    return datetime.fromtimestamp(add_date).strftime("%Y-%m-%d")


def unix_to_date(ts: int, fmt: str = "%Y-%m-%d") -> str:
    """
    Generic unix timestamp -> date string formatter.
    Useful if you later want different formats in reports/HTML titles.
    """
    if not ts:
        return "unknown"
    return datetime.fromtimestamp(ts).strftime(fmt)
