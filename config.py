from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# -----------------------------
# Defaults (single source of truth)
# -----------------------------
DEFAULT_BOOKMARKS_HTML = r"F:/Dropbox/Tools/bookmarks_1_15_26.html"
DEFAULT_OUTPUT_CSV = r"F:/Dropbox/Tools/bookmark_link_check_results.csv"

DEFAULT_MAX_LINKS = 0
DEFAULT_TIMEOUT_CONNECT = 4
DEFAULT_TIMEOUT_READ = 10

DEFAULT_ENABLE_SOFT_404 = False
DEFAULT_ENABLE_FINGERPRINTING = False

DEFAULT_DEDUPE_MODE = "strict"  # strict|basic|tracking_free|aggressive

DEFAULT_WORKERS = 15
DEFAULT_PER_DOMAIN_DELAY_SEC = 1.0

DEFAULT_IGNORE_DOMAINS: List[str] = []
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_CONFIG_PATH = "config.yaml"


@dataclass
class AppConfig:
    """
    Final resolved settings used by the program.
    This is what main.py should rely on after parsing + merging.
    """
    bookmarks: str = DEFAULT_BOOKMARKS_HTML
    out: str = DEFAULT_OUTPUT_CSV
    max_links: int = DEFAULT_MAX_LINKS

    timeout_connect: int = DEFAULT_TIMEOUT_CONNECT
    timeout_read: int = DEFAULT_TIMEOUT_READ

    enable_soft_404: bool = DEFAULT_ENABLE_SOFT_404
    enable_fingerprinting: bool = DEFAULT_ENABLE_FINGERPRINTING

    dedupe_mode: str = DEFAULT_DEDUPE_MODE

    workers: int = DEFAULT_WORKERS
    per_domain_delay: float = DEFAULT_PER_DOMAIN_DELAY_SEC

    ignore_domain: List[str] = None  # filled in __post_init__

    log_level: str = DEFAULT_LOG_LEVEL
    config_path: str = DEFAULT_CONFIG_PATH

    def __post_init__(self):
        if self.ignore_domain is None:
            self.ignore_domain = list(DEFAULT_IGNORE_DOMAINS)


def load_yaml_config(path: Path) -> Dict[str, Any]:
    """Load YAML config. Missing file => empty dict."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _as_list(value: Any) -> List[str]:
    """Normalize config values that might be a scalar or list into a list[str]."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def build_config_from_args_and_yaml(args, cfg: Dict[str, Any]) -> AppConfig:
    """
    Merge defaults + YAML + CLI into a final AppConfig.

    Rules:
    - CLI wins over YAML
    - YAML wins over defaults
    - ignore_domain merges YAML + CLI (unique)
    - boolean flags: only YAML applies if CLI did NOT enable it
      (matches your previous behavior)
    """
    # Start from defaults
    out = AppConfig()

    # Record where config came from
    out.config_path = getattr(args, "config", DEFAULT_CONFIG_PATH) or DEFAULT_CONFIG_PATH
    out.log_level = getattr(args, "log_level", DEFAULT_LOG_LEVEL) or DEFAULT_LOG_LEVEL

    # --------
    # YAML layer
    # --------
    # Only apply YAML if CLI still at default values (or equivalent)
    # Paths
    if getattr(args, "bookmarks", DEFAULT_BOOKMARKS_HTML) == DEFAULT_BOOKMARKS_HTML:
        out.bookmarks = cfg.get("bookmarks_html", out.bookmarks)
    if getattr(args, "out", DEFAULT_OUTPUT_CSV) == DEFAULT_OUTPUT_CSV:
        out.out = cfg.get("output_csv", out.out)

    # Performance / timeouts
    if getattr(args, "workers", DEFAULT_WORKERS) == DEFAULT_WORKERS:
        out.workers = int(cfg.get("workers", out.workers))
    if getattr(args, "per_domain_delay", DEFAULT_PER_DOMAIN_DELAY_SEC) == DEFAULT_PER_DOMAIN_DELAY_SEC:
        out.per_domain_delay = float(cfg.get("per_domain_delay", out.per_domain_delay))

    if getattr(args, "timeout_connect", DEFAULT_TIMEOUT_CONNECT) == DEFAULT_TIMEOUT_CONNECT:
        out.timeout_connect = int(cfg.get("timeout_connect", out.timeout_connect))
    if getattr(args, "timeout_read", DEFAULT_TIMEOUT_READ) == DEFAULT_TIMEOUT_READ:
        out.timeout_read = int(cfg.get("timeout_read", out.timeout_read))

    # Dedupe mode
    if getattr(args, "dedupe_mode", DEFAULT_DEDUPE_MODE) == DEFAULT_DEDUPE_MODE:
        out.dedupe_mode = str(cfg.get("dedupe_mode", out.dedupe_mode))

    # Max links
    if getattr(args, "max_links", DEFAULT_MAX_LINKS) == DEFAULT_MAX_LINKS:
        out.max_links = int(cfg.get("max_links", out.max_links))

    # Boolean flags: YAML only if CLI didn't enable them
    if not bool(getattr(args, "enable_soft_404", False)):
        out.enable_soft_404 = bool(cfg.get("enable_soft_404", out.enable_soft_404))
    else:
        out.enable_soft_404 = True

    if not bool(getattr(args, "enable_fingerprinting", False)):
        out.enable_fingerprinting = bool(cfg.get("enable_fingerprinting", out.enable_fingerprinting))
    else:
        out.enable_fingerprinting = True

    # Ignore domains merge (YAML + CLI unique, preserve order)
    yaml_ignores = _as_list(cfg.get("ignore_domains", []))
    cli_ignores = _as_list(getattr(args, "ignore_domain", []))
    merged = list(dict.fromkeys(yaml_ignores + cli_ignores))
    out.ignore_domain = merged

    # --------
    # CLI layer (explicit overrides)
    # --------
    # Anything that isn't at its default is treated as an override.
    if getattr(args, "bookmarks", DEFAULT_BOOKMARKS_HTML) != DEFAULT_BOOKMARKS_HTML:
        out.bookmarks = args.bookmarks
    if getattr(args, "out", DEFAULT_OUTPUT_CSV) != DEFAULT_OUTPUT_CSV:
        out.out = args.out

    if getattr(args, "workers", DEFAULT_WORKERS) != DEFAULT_WORKERS:
        out.workers = int(args.workers)
    if getattr(args, "per_domain_delay", DEFAULT_PER_DOMAIN_DELAY_SEC) != DEFAULT_PER_DOMAIN_DELAY_SEC:
        out.per_domain_delay = float(args.per_domain_delay)

    if getattr(args, "timeout_connect", DEFAULT_TIMEOUT_CONNECT) != DEFAULT_TIMEOUT_CONNECT:
        out.timeout_connect = int(args.timeout_connect)
    if getattr(args, "timeout_read", DEFAULT_TIMEOUT_READ) != DEFAULT_TIMEOUT_READ:
        out.timeout_read = int(args.timeout_read)

    if getattr(args, "dedupe_mode", DEFAULT_DEDUPE_MODE) != DEFAULT_DEDUPE_MODE:
        out.dedupe_mode = str(args.dedupe_mode)

    if getattr(args, "max_links", DEFAULT_MAX_LINKS) != DEFAULT_MAX_LINKS:
        out.max_links = int(args.max_links)

    # log_level: always let CLI win if user provided it (argparse default makes this tricky)
    if getattr(args, "log_level", DEFAULT_LOG_LEVEL) != DEFAULT_LOG_LEVEL:
        out.log_level = args.log_level

    return out
