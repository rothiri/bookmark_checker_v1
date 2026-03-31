# bookmark_checker/models.py
"""
Data models for the bookmark checker pipeline.

Goals:
- Keep models simple and serializable.
- Make it easy to convert to/from dicts for CSV/HTML writers.
- Avoid networking concerns here (pure data).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Bookmark:
    """
    A parsed bookmark entry from Chrome export HTML.
    """
    title: str
    url: str
    folder_path: str = ""
    add_date: int = 0  # Chrome ADD_DATE (unix epoch seconds), 0 if missing


@dataclass(frozen=True)
class RetryMeta:
    """
    Metadata returned by retry wrapper logic.
    """
    retried: bool = False
    retry_count: int = 0
    retry_history: str = ""


@dataclass(frozen=True)
class CheckResult:
    """
    One normalized result row produced by the worker.

    This is intentionally "CSV-shaped" to make writing outputs trivial.
    """
    folder_path: str
    title: str
    input_url: str
    final_url: str = ""
    status_code: str = ""
    ok: bool = False
    error_type: str = ""
    notes: str = ""
    add_date: int = 0
    retried: bool = False
    retry_count: int = 0
    retry_history: str = ""

    def to_csv_row(self) -> Dict[str, Any]:
        """
        DictWriter-friendly row.
        """
        return {
            "folder_path": self.folder_path,
            "title": self.title,
            "input_url": self.input_url,
            "final_url": self.final_url,
            "status_code": self.status_code,
            "ok": self.ok,
            "error_type": self.error_type,
            "notes": self.notes,
            "retried": self.retried,
            "retry_count": int(self.retry_count),
            "retry_history": self.retry_history,
        }

    @classmethod
    def from_worker_dict(cls, d: Dict[str, Any]) -> "CheckResult":
        """
        Convert an existing worker-produced dict (your current structure) into a model.
        This lets you adopt models incrementally without big refactors.
        """
        return cls(
            folder_path=str(d.get("folder_path", "") or ""),
            title=str(d.get("title", "") or ""),
            input_url=str(d.get("input_url", "") or ""),
            final_url=str(d.get("final_url", "") or ""),
            status_code=str(d.get("status_code", "") or ""),
            ok=bool(d.get("ok", False)),
            error_type=str(d.get("error_type", "") or ""),
            notes=str(d.get("notes", "") or ""),
            add_date=int(d.get("add_date", 0) or 0),
            retried=bool(d.get("retried", False)),
            retry_count=int(d.get("retry_count", 0) or 0),
            retry_history=str(d.get("retry_history", "") or ""),
        )


def bookmark_from_dict(d: Dict[str, Any]) -> Bookmark:
    """
    Convenience for converting your current parse dicts into Bookmark models.
    """
    return Bookmark(
        title=str(d.get("title", "") or ""),
        url=str(d.get("url", "") or ""),
        folder_path=str(d.get("folder_path", "") or ""),
        add_date=int(d.get("add_date", 0) or 0),
    )


def bookmark_to_dict(bm: Bookmark) -> Dict[str, Any]:
    """
    Convert Bookmark model back to dict (useful until you fully migrate).
    """
    return asdict(bm)
