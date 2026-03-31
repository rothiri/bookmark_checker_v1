# dedupe.py
"""
URL deduplication utilities.

Implements multiple dedupe modes:
- strict: exact string match
- basic: normalize scheme + www, basic host/path cleanup
- tracking_free: basic + remove common tracking params (utm_*, gclid, fbclid, etc.)
- aggressive: tracking_free + drop fragments + sort query params for stable equivalence

Design goals:
- Deterministic dedupe keys
- Small, testable functions
- No networking, no side effects
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# ---- Public API ----------------------------------------------------------------


DEDUPE_MODES = {"strict", "basic", "tracking_free", "aggressive"}


@dataclass(frozen=True)
class DedupeStats:
    mode: str
    total_in: int
    unique_out: int
    duplicates: int
    # Map: duplicate_key -> canonical_key (the first-seen key)
    dup_key_to_canonical_key: Dict[str, str]
    # Map: duplicate_url -> canonical_url (human friendly for logs/debug)
    dup_url_to_canonical_url: Dict[str, str]


def make_dedupe_key(url: str, mode: str) -> str:
    """
    Produce a stable, comparable key for a URL according to the chosen dedupe mode.
    """
    mode = (mode or "strict").strip().lower()
    if mode not in DEDUPE_MODES:
        raise ValueError(f"Unknown dedupe mode: {mode!r}. Expected one of: {sorted(DEDUPE_MODES)}")

    raw = (url or "").strip()
    if not raw:
        return ""  # empty stays empty; caller can decide how to handle

    if mode == "strict":
        return raw

    # For non-strict modes, we normalize using a parsed URL.
    # If scheme is missing, urlsplit treats it as path; we'll coerce into http:// for parsing only.
    parsed = _safe_urlsplit(raw)
    normalized = _normalize_basic(parsed)

    if mode == "basic":
        return _to_key(normalized)

    tracking_free = _remove_tracking_params(normalized)
    if mode == "tracking_free":
        return _to_key(tracking_free)

    # aggressive
    aggressive = _normalize_aggressive(tracking_free)
    return _to_key(aggressive)


def dedupe_bookmarks(
    bookmarks: Iterable[Any],
    mode: str,
) -> Tuple[List[Any], DedupeStats]:
    """
    Deduplicate bookmarks by URL using the specified mode.

    The bookmark object can be:
      - a dataclass/object with .input_url or .url
      - a dict with 'input_url' or 'url'

    Returns:
      (deduped_bookmarks, stats)
    """
    mode = (mode or "strict").strip().lower()
    if mode not in DEDUPE_MODES:
        raise ValueError(f"Unknown dedupe mode: {mode!r}. Expected one of: {sorted(DEDUPE_MODES)}")

    seen_key_to_bookmark: Dict[str, Any] = {}
    seen_key_to_canonical_url: Dict[str, str] = {}

    dup_key_to_canonical_key: Dict[str, str] = {}
    dup_url_to_canonical_url: Dict[str, str] = {}

    total = 0
    for bm in bookmarks:
        total += 1
        url = _get_bookmark_url(bm)
        key = make_dedupe_key(url, mode)

        # Treat empty-key as unique (keeps weird/blank bookmark entries visible)
        if key == "":
            unique_key = f"__empty__:{total}"
            seen_key_to_bookmark[unique_key] = bm
            seen_key_to_canonical_url[unique_key] = url
            continue

        if key in seen_key_to_bookmark:
            dup_key_to_canonical_key[key] = key
            dup_url_to_canonical_url[url] = seen_key_to_canonical_url.get(key, "")
            continue

        seen_key_to_bookmark[key] = bm
        seen_key_to_canonical_url[key] = url

    deduped = list(seen_key_to_bookmark.values())
    stats = DedupeStats(
        mode=mode,
        total_in=total,
        unique_out=len(deduped),
        duplicates=total - len(deduped),
        dup_key_to_canonical_key=dup_key_to_canonical_key,
        dup_url_to_canonical_url=dup_url_to_canonical_url,
    )
    return deduped, stats


# ---- Internals ----------------------------------------------------------------


TRACKING_PARAMS_EXACT = {
    "gclid",
    "fbclid",
    "msclkid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "yclid",
    "dclid",
    "gbraid",
    "wbraid",
    "vero_conv",
    "vero_id",
}

TRACKING_PREFIXES = (
    "utm_",          # utm_source, utm_medium, etc.
    "pk_",           # piwik/proprietary
    "spm",           # alibaba/others
    "ref_",          # various
)


def _get_bookmark_url(bm: Any) -> str:
    """
    Robustly extract a URL from different bookmark representations.
    """
    if bm is None:
        return ""
    # dict-like
    if isinstance(bm, dict):
        return str(bm.get("input_url") or bm.get("url") or "")
    # object-like
    if hasattr(bm, "input_url"):
        return str(getattr(bm, "input_url") or "")
    if hasattr(bm, "url"):
        return str(getattr(bm, "url") or "")
    # fallback: best-effort string conversion
    return str(bm)


def _safe_urlsplit(raw: str):
    """
    urlsplit requires a scheme to reliably place netloc. If missing, coerce with http:// for parsing.
    We keep the *original* scheme if it exists.
    """
    p = urlsplit(raw)
    if p.scheme or p.netloc:
        return p
    # If no scheme/netloc, try coercion for parse only
    coerced = urlsplit("http://" + raw)
    # keep original raw scheme absent; we'll normalize anyway
    return coerced


def _normalize_basic(p) -> Tuple[str, str, str, str, str]:
    """
    Basic normalization:
    - lowercase scheme + host
    - drop leading 'www.'
    - remove default ports for http/https
    - normalize empty path to '/'
    - keep query + fragment (handled in later modes)
    """
    scheme = (p.scheme or "http").lower().strip()

    netloc = (p.netloc or "").strip()
    netloc_lower = netloc.lower()

    # If urlsplit placed everything in path (rare after coercion), try to recover
    path = (p.path or "").strip()

    # Strip credentials if any (rare in bookmarks; also reduces key variance)
    if "@" in netloc_lower:
        netloc_lower = netloc_lower.split("@", 1)[1]

    host, port = _split_host_port(netloc_lower)

    if host.startswith("www."):
        host = host[4:]

    # Drop default ports
    if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
        port = ""

    netloc_norm = host if not port else f"{host}:{port}"

    if not path:
        path = "/"

    # Avoid path-only differences from trailing slashes on "file-like" paths
    # (Keep it conservative; do not remove trailing slash universally.)
    query = (p.query or "").strip()
    fragment = (p.fragment or "").strip()

    return scheme, netloc_norm, path, query, fragment


def _remove_tracking_params(parts: Tuple[str, str, str, str, str]) -> Tuple[str, str, str, str, str]:
    scheme, netloc, path, query, fragment = parts
    if not query:
        return parts

    kv = parse_qsl(query, keep_blank_values=True)

    filtered: List[Tuple[str, str]] = []
    for k, v in kv:
        k_l = k.lower()
        if k_l in TRACKING_PARAMS_EXACT:
            continue
        if any(k_l.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        filtered.append((k, v))

    new_query = urlencode(filtered, doseq=True)
    return scheme, netloc, path, new_query, fragment


def _normalize_aggressive(parts: Tuple[str, str, str, str, str]) -> Tuple[str, str, str, str, str]:
    """
    Aggressive normalization:
    - drop fragment
    - sort query params (stable ordering)
    """
    scheme, netloc, path, query, _fragment = parts

    if query:
        kv = parse_qsl(query, keep_blank_values=True)
        kv_sorted = sorted(kv, key=lambda t: (t[0].lower(), t[1]))
        query = urlencode(kv_sorted, doseq=True)

    fragment = ""  # drop
    return scheme, netloc, path, query, fragment


def _to_key(parts: Tuple[str, str, str, str, str]) -> str:
    """
    Convert normalized parts back into a canonical string.
    """
    scheme, netloc, path, query, fragment = parts
    return urlunsplit((scheme, netloc, path, query, fragment))


def _split_host_port(netloc: str) -> Tuple[str, str]:
    """
    Split host:port safely for typical bookmark URLs.
    (IPv6 in brackets isn't expected from Chrome bookmarks commonly; handle lightly.)
    """
    if not netloc:
        return "", ""

    # IPv6 like [::1]:8080
    if netloc.startswith("[") and "]" in netloc:
        host_end = netloc.index("]") + 1
        host = netloc[:host_end]
        rest = netloc[host_end:]
        if rest.startswith(":"):
            return host, rest[1:]
        return host, ""

    if ":" in netloc:
        host, port = netloc.rsplit(":", 1)
        if port.isdigit():
            return host, port
        # not a port; keep as host
        return netloc, ""
    return netloc, ""
