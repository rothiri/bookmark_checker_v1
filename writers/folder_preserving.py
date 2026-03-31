from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Iterable

from bookmark_checker.models import Bookmark


def write_folder_preserving_valid_bookmarks_html(
    bookmarks: Iterable[Bookmark],
    output_path: str | Path,
) -> None:
    """
    Write a Chrome-importable bookmarks HTML file that keeps the
    original folder structure.

    Important:
    This function expects to receive bookmarks that are already valid.
    main.py is doing the filtering before calling this writer.
    """
    output_path = Path(output_path)

    tree = build_folder_tree(bookmarks)
    html_text = render_bookmark_tree_html(tree)

    output_path.write_text(html_text, encoding="utf-8")


def build_folder_tree(bookmarks: Iterable[Bookmark]) -> dict[str, Any]:
    root = make_folder_node()

    for bm in bookmarks:
        path_parts = normalize_folder_path(bm.folder_path)

        current = root
        for part in path_parts:
            current = current["children"].setdefault(part, make_folder_node())

        current["bookmarks"].append(bm)

    return root


def make_folder_node() -> dict[str, Any]:
    return {
        "children": {},
        "bookmarks": [],
    }


def normalize_folder_path(folder_path: Any) -> list[str]:
    """
    Handle a few possible folder_path formats safely.
    """
    if folder_path is None:
        return []

    if isinstance(folder_path, (list, tuple)):
        return [str(part).strip() for part in folder_path if str(part).strip()]

    if isinstance(folder_path, str):
        if " > " in folder_path:
            return [part.strip() for part in folder_path.split(" > ") if part.strip()]
        if "/" in folder_path:
            return [part.strip() for part in folder_path.split("/") if part.strip()]
        return [folder_path.strip()] if folder_path.strip() else []

    return [str(folder_path).strip()]


def render_bookmark_tree_html(tree: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("<!DOCTYPE NETSCAPE-Bookmark-file-1>")
    lines.append("<!-- This is an automatically generated file.")
    lines.append("     It will be read and overwritten.")
    lines.append("     DO NOT EDIT! -->")
    lines.append('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">')
    lines.append("<TITLE>Bookmarks</TITLE>")
    lines.append("<H1>Bookmarks</H1>")
    lines.append("<DL><p>")

    for folder_name, folder_node in sorted(
        tree["children"].items(),
        key=lambda item: item[0].lower(),
    ):
        render_folder(lines, folder_name, folder_node, indent=1)

    for bm in sorted(tree["bookmarks"], key=lambda item: (item.title or "").lower()):
        render_bookmark(lines, bm, indent=1)

    lines.append("</DL><p>")

    return "\n".join(lines)


def render_folder(
    lines: list[str],
    folder_name: str,
    node: dict[str, Any],
    indent: int = 0,
) -> None:
    prefix = "    " * indent
    safe_folder_name = escape(folder_name)

    lines.append(f"{prefix}<DT><H3>{safe_folder_name}</H3>")
    lines.append(f"{prefix}<DL><p>")

    for child_name, child_node in sorted(
        node["children"].items(),
        key=lambda item: item[0].lower(),
    ):
        render_folder(lines, child_name, child_node, indent + 1)

    for bm in sorted(node["bookmarks"], key=lambda item: (item.title or "").lower()):
        render_bookmark(lines, bm, indent + 1)

    lines.append(f"{prefix}</DL><p>")


def render_bookmark(lines: list[str], bm: Bookmark, indent: int = 0) -> None:
    prefix = "    " * indent

    title = bm.title or bm.url or "Untitled"
    url = bm.url or ""

    safe_title = escape(title)
    safe_url = escape(url, quote=True)

    add_date_attr = ""
    if getattr(bm, "add_date", None):
        add_date_attr = f' ADD_DATE="{bm.add_date}"'

    icon_attr = ""
    if getattr(bm, "icon", None):
        icon_attr = f' ICON="{escape(bm.icon, quote=True)}"'

    lines.append(
        f'{prefix}<DT><A HREF="{safe_url}"{add_date_attr}{icon_attr}>{safe_title}</A>'
    )