# bookmark_checker/normalize.py
"""
URL normalization helpers.

Purpose:
- Provide deterministic, testable URL canonicalization
- Shared logic for dedupe, grouping, reporting, and skip rules
- No networking, no side effects

Modes align with dedupe modes:
- strict
- basic
- tracking_free
- aggressive
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit


DEFAULT_TRACKING_PARAMS_EXACT = {
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

DEFAULT_TRACKING_PREFIXES = (
    "utm_",  # utm_source, utm_medium, etc.
    "pk_",   # piwik
    "ref_",  # many sites
)


DEDUPE_MODES = {"strict", "basic", "tracking_free", "aggressive"}


@dataclass(frozen=True)
class NormalizeOptions:
    """
    Options to tune normalization behavior.

    These defaults are conservative and web-safe.
    If you want to match your earlier main.py behavior exactly:
      - force_https=True
      - strip_trailing_slash=True
    """
    force_https: bool = False
    strip_www: bool = True
    strip_default_ports: bool = True
    strip_trailing_slash: bool = False  # only for non-root paths
    ensure_path_slash: bool = True      # empty path -> "/"
    drop_fragment_in_aggressive: bool = True


def canonical_domain(url: str) -> str:
    """
    Canonical domain key used for grouping and politeness throttling.
    Strips leading www. and lowercases.

    Returns 'unknown-domain' if it can't be derived.
    """
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return "unknown-domain"

    if host.startswith("www."):
        host = host[4:]
    return host or "unknown-domain"


def normalize_url(
    url: str,
    mode: str = "basic",
    *,
    opts: NormalizeOptions | None = None,
    tracking_exact: Iterable[str] = DEFAULT_TRACKING_PARAMS_EXACT,
    tracking_prefixes: Iterable[str] = DEFAULT_TRACKING_PREFIXES,
) -> str:
    """
    Normalize a URL according to the dedupe mode.

    strict:
      - returns original trimmed string (no parsing/normalizing)
    basic:
      - lowercases scheme/netloc
      - optionally strips www
      - optionally strips default ports
      - optionally forces https
      - optional trailing slash trim
    tracking_free:
      - basic + remove known tracking params
    aggressive:
      - tracking_free + stable sort query params + optionally drop fragment

    Notes:
    - If url has no scheme, it's parsed as http:// for parsing only.
    - Does not validate reachability.
    """
    mode = (mode or "basic").strip().lower()
    if mode not in DEDUPE_MODES:
        raise ValueError(f"Unknown normalize mode: {mode!r}. Expected one of: {sorted(DEDUPE_MODES)}")

    raw = (url or "").strip()
    if not raw or mode == "strict":
        return raw

    opts = opts or NormalizeOptions()

    p = _safe_urlsplit(raw)
    scheme, netloc, path, query, fragment = _normalize_basic_parts(p, opts=opts)

    if mode in ("tracking_free", "aggressive"):
        query = _remove_tracking_from_query(query, tracking_exact, tracking_prefixes)

    if mode == "aggressive":
        query = _sort_query_params(query)
        if opts.drop_fragment_in_aggressive:
            fragment = ""

    return urlunsplit((scheme, netloc, path, query, fragment))


# -------------------------
# Internals
# -------------------------

def _safe_urlsplit(raw: str):
    """
    Ensure urlsplit gets a netloc when possible.
    If the scheme is missing, prefix with http:// for parsing only.
    """
    p = urlsplit(raw)
    if p.scheme or p.netloc:
        return p
    return urlsplit("http://" + raw)


def _normalize_basic_parts(p, *, opts: NormalizeOptions) -> Tuple[str, str, str, str, str]:
    scheme = (p.scheme or "http").lower().strip()
    netloc = (p.netloc or "").strip().lower()
    path = (p.path or "").strip()
    query = (p.query or "").strip()
    fragment = (p.fragment or "").strip()

    if opts.force_https and scheme == "http":
        scheme = "https"

    # Strip credentials if present (rare; reduces key variance)
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]

    host, port = _split_host_port(netloc)

    if opts.strip_www and host.startswith("www."):
        host = host[4:]

    if opts.strip_default_ports:
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            port = ""

    netloc = host if not port else f"{host}:{port}"

    if opts.ensure_path_slash and not path:
        path = "/"

    if opts.strip_trailing_slash and path != "/" and path.endswith("/"):
        path = path[:-1]

    return scheme, netloc, path, query, fragment


def _remove_tracking_from_query(
    query: str,
    tracking_exact: Iterable[str],
    tracking_prefixes: Iterable[str],
) -> str:
    if not query:
        return query

    exact = {k.lower() for k in tracking_exact}
    prefixes = tuple(p.lower() for p in tracking_prefixes)

    kv = parse_qsl(query, keep_blank_values=True)
    kept: List[Tuple[str, str]] = []
    for k, v in kv:
        kl = k.lower()
        if kl in exact:
            continue
        if any(kl.startswith(pref) for pref in prefixes):
            continue
        kept.append((k, v))

    return urlencode(kept, doseq=True)


def _sort_query_params(query: str) -> str:
    if not query:
        return query
    kv = parse_qsl(query, keep_blank_values=True)
    kv_sorted = sorted(kv, key=lambda t: (t[0].lower(), t[1]))
    return urlencode(kv_sorted, doseq=True)


def _split_host_port(netloc: str) -> Tuple[str, str]:
    """
    Split host:port safely for common URLs.
    Handles IPv6 bracket format lightly.
    """
    if not netloc:
        return "", ""

    # IPv6: [::1]:8080
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
        return netloc, ""

    return netloc, ""
