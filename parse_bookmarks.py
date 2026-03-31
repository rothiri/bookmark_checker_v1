# bookmark_checker/parse_bookmarks.py
"""
Parse Chrome bookmark export HTML into Bookmark models.

Supports:
- http/https links only (skips javascript:, chrome:, file:, etc.)
- ADD_DATE parsing (unix seconds; 0 if missing)
- Folder extraction:
    - shallow: nearest previous H3 (matches your current behavior)
    - deep: build full nested folder path by walking ancestor DL/DT structure

Design:
- No side effects
- No logging here (caller logs counts)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup
from urllib.parse import urlparse

from bookmark_checker.models import Bookmark


@dataclass(frozen=True)
class ParseOptions:
    """
    Parsing options.
    """
    folder_mode: str = "shallow"  # "shallow" | "deep"
    encoding: str = "utf-8"
    errors: str = "ignore"


def parse_bookmarks_html(html_path: Path, *, opts: ParseOptions | None = None) -> List[Bookmark]:
    """
    Parse Chrome exported bookmarks HTML to a list of Bookmark models.
    """
    opts = opts or ParseOptions()

    text = html_path.read_text(encoding=opts.encoding, errors=opts.errors)
    soup = BeautifulSoup(text, "html.parser")

    bookmarks: List[Bookmark] = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        scheme = (urlparse(href).scheme or "").lower()
        if scheme not in ("http", "https"):
            continue

        title = a.get_text(strip=True) or ""

        add_date_str = a.get("add_date") or a.get("ADD_DATE") or ""
        try:
            add_date = int(add_date_str) if add_date_str else 0
        except ValueError:
            add_date = 0

        if opts.folder_mode == "deep":
            folder_path = _folder_path_deep(a)
        else:
            folder_path = _folder_path_shallow(a)

        bookmarks.append(
            Bookmark(
                title=title,
                url=href,
                folder_path=folder_path,
                add_date=add_date,
            )
        )

    return bookmarks


# -------------------------
# Folder path helpers
# -------------------------

def _folder_path_shallow(a_tag) -> str:
    """
    Matches your current logic:
    - find parent DT
    - take the nearest previous H3 text
    """
    folder = ""
    dt = a_tag.find_parent("dt")
    if dt:
        prev_h3 = dt.find_previous("h3")
        if prev_h3:
            folder = prev_h3.get_text(strip=True)
    return folder or ""


def _folder_path_deep(a_tag) -> str:
    """
    Build a nested folder path like:
        Parent/Child/Subchild

    This walks upward looking for containing folder headings (H3).
    Chrome bookmark exports use nested:
        <DT><H3>Folder</H3>
        <DL><p> ... bookmarks and folders ... </DL><p>
    """
    # We walk up through parent nodes, collecting H3s that "own" our DT/DL.
    # This is best-effort because exports vary slightly.
    parts: List[str] = []

    # Start at the <DT> that contains the <A>
    node = a_tag.find_parent("dt")
    if node is None:
        return ""

    # Walk up: DT -> DL -> (previous sibling DT with H3) -> DL -> ...
    current = node
    while current is not None:
        dl = current.find_parent("dl")
        if dl is None:
            break

        # The folder heading is usually in a preceding DT that contains an H3
        folder_dt = dl.find_previous_sibling("dt")
        if folder_dt:
            h3 = folder_dt.find("h3")
            if h3:
                name = h3.get_text(strip=True)
                if name:
                    parts.append(name)

        # Move up one level: the DL's parent DT (folder container)
        current = dl.find_parent("dt")

    parts.reverse()
    return "/".join(parts)
