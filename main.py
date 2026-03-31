"""
bookmark_checker/main.py

Main pipeline for the bookmark checker:

1. Parse Chrome bookmarks HTML
2. Deduplicate URLs
3. Check URLs in parallel
4. Respect per-domain politeness delay
5. Retry transient failures with backoff
6. Write outputs:
   - CSV
   - flat valid bookmarks HTML
   - grouped-by-domain valid bookmarks HTML
   - folder-preserving valid bookmarks HTML
   - Markdown report
"""

from __future__ import annotations

import argparse
import csv
import html as html_escape
import logging
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import local
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from bookmark_checker.checks.http_check import check_url_once
from bookmark_checker.checks.politeness import polite_wait_domain
from bookmark_checker.checks.retry import RetryConfig, check_url_with_retries

from bookmark_checker.config import (
    DEFAULT_BOOKMARKS_HTML,
    DEFAULT_OUTPUT_CSV,
    DEFAULT_MAX_LINKS,
    DEFAULT_TIMEOUT_CONNECT,
    DEFAULT_TIMEOUT_READ,
    DEFAULT_ENABLE_SOFT_404,
    DEFAULT_ENABLE_FINGERPRINTING,
    DEFAULT_DEDUPE_MODE,
    DEFAULT_WORKERS,
    DEFAULT_PER_DOMAIN_DELAY_SEC,
    DEFAULT_IGNORE_DOMAINS,
    load_yaml_config,
    build_config_from_args_and_yaml,
)

from bookmark_checker.dedupe import dedupe_bookmarks as dedupe_bookmarks_mod
from bookmark_checker.models import Bookmark, CheckResult
from bookmark_checker.normalize import canonical_domain
from bookmark_checker.parse_bookmarks import parse_bookmarks_html

from bookmark_checker.utils.dates import human_date_from_add_date
from bookmark_checker.utils.logging import setup_logging
from bookmark_checker.utils.paths import ensure_parent_dir, derive_output_paths

from bookmark_checker.writers.folder_preserving import (
    write_folder_preserving_valid_bookmarks_html,
)

# One requests Session per thread.
# This keeps connections reusable without sharing one Session across all workers.
_thread_local = local()


# --------------------------------------------------
# URL helpers
# --------------------------------------------------
def should_skip_url(url: str, ignore_domains: List[str]) -> Tuple[bool, str]:
    """
    Skip unsupported URLs early so we do not waste time trying to check them.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return True, "invalid_url_parse"

    if parsed.scheme.lower() not in ("http", "https"):
        return True, "non_http_scheme"

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]

    for domain in ignore_domains:
        clean_domain = domain.lower()
        if clean_domain.startswith("www."):
            clean_domain = clean_domain[4:]

        if host == clean_domain or host.endswith("." + clean_domain):
            return True, f"ignored_domain:{domain}"

    return False, ""


# --------------------------------------------------
# Session handling
# --------------------------------------------------
def get_session() -> requests.Session:
    """
    Return a persistent Session object for the current worker thread.
    """
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


# --------------------------------------------------
# Output writers
# --------------------------------------------------
def write_chrome_bookmarks_html(
    bookmarks: List[Bookmark],
    out_html_path: Path,
    folder_name: str,
) -> None:
    """
    Write a simple Chrome-importable bookmarks HTML file.
    This is the flat valid-links export.
    """
    import time
    from datetime import datetime

    now = int(time.time())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<!-- This is an automatically generated file. -->",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        f"<!-- Generated: {timestamp} -->",
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
        f'  <DT><H3 ADD_DATE="{now}" LAST_MODIFIED="{now}">{html_escape.escape(folder_name)}</H3>',
        "  <DL><p>",
    ]

    for bm in bookmarks:
        title = bm.title or bm.url or ""
        url = bm.url or ""
        add_date = int(bm.add_date or 0) or now

        lines.append(
            f'    <DT><A HREF="{html_escape.escape(url)}" ADD_DATE="{add_date}">'
            f"{html_escape.escape(title)}</A>"
        )

    lines.extend([
        "  </DL><p>",
        "</DL><p>",
    ])

    out_html_path.write_text("\n".join(lines), encoding="utf-8")


def write_valid_grouped_by_domain(
    valid_bookmarks: List[Bookmark],
    out_html_path: Path,
    root_folder: str,
) -> None:
    """
    Write a Chrome-importable bookmarks HTML file grouped by domain.
    Bookmarks inside each domain are sorted oldest first.
    """
    import time

    now = int(time.time())

    groups: Dict[str, List[Bookmark]] = defaultdict(list)
    for bm in valid_bookmarks:
        groups[canonical_domain(bm.url)].append(bm)

    domain_names = sorted(groups.keys())

    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
        f'  <DT><H3 ADD_DATE="{now}" LAST_MODIFIED="{now}">{html_escape.escape(root_folder)}</H3>',
        "  <DL><p>",
    ]

    for domain in domain_names:
        items = groups[domain]
        items.sort(key=lambda x: (int(x.add_date or 0), (x.title or "").lower()))

        lines.append(
            f'    <DT><H3 ADD_DATE="{now}" LAST_MODIFIED="{now}">{html_escape.escape(domain)}</H3>'
        )
        lines.append("    <DL><p>")

        for bm in items:
            add_date = int(bm.add_date or 0)
            date_prefix = human_date_from_add_date(add_date)
            title = bm.title or bm.url or ""
            title = f"({date_prefix}) {title}"

            url = bm.url or ""
            add_date_attr = add_date or now

            lines.append(
                f'      <DT><A HREF="{html_escape.escape(url)}" ADD_DATE="{add_date_attr}">'
                f"{html_escape.escape(title)}</A>"
            )

        lines.append("    </DL><p>")

    lines.extend([
        "  </DL><p>",
        "</DL><p>",
    ])

    out_html_path.write_text("\n".join(lines), encoding="utf-8")


def write_report_md(
    report_path: Path,
    total_processed: int,
    ok_count: int,
    error_counts: Counter,
    fail_domain_counts: Counter,
) -> None:
    """
    Write a small Markdown report for quick review.
    """
    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write("# Bookmark Link Check Report\n\n")
        report_file.write(f"- Total checked: {total_processed}\n")
        report_file.write(f"- OK: {ok_count}\n")
        report_file.write(f"- Fail: {total_processed - ok_count}\n\n")

        report_file.write("## Top error types\n")
        for error_name, count in error_counts.most_common(25):
            report_file.write(f"- {error_name}: {count}\n")

        report_file.write("\n## Top failing domains\n")
        for domain, count in fail_domain_counts.most_common(25):
            report_file.write(f"- {domain}: {count}\n")


# --------------------------------------------------
# Worker
# --------------------------------------------------
def process_one_bookmark(
    bm: Any,
    ignore_domains: List[str],
    timeout: Tuple[int, int],
    enable_soft_404: bool,
    enable_fingerprinting: bool,
    per_domain_delay: float,
    retry_cfg: RetryConfig,
) -> Dict[str, Any]:
    """
    Check one bookmark in a worker thread.

    Still supports Bookmark models and dicts because migrations always
    sound easier than they actually are.
    """
    url = getattr(bm, "url", None) or (bm.get("url") if isinstance(bm, dict) else "")
    title = getattr(bm, "title", None) or (bm.get("title") if isinstance(bm, dict) else "")
    folder_path = getattr(bm, "folder_path", None) or (
        bm.get("folder_path") if isinstance(bm, dict) else ""
    )

    add_date = getattr(bm, "add_date", None)
    if add_date is None and isinstance(bm, dict):
        add_date = bm.get("add_date", 0)
    add_date = int(add_date or 0)

    skip, reason = should_skip_url(url, ignore_domains)
    if skip:
        return {
            "folder_path": folder_path,
            "title": title,
            "input_url": url,
            "final_url": "",
            "status_code": "",
            "ok": False,
            "error_type": reason,
            "notes": "",
            "add_date": add_date,
            "retried": False,
            "retry_count": 0,
            "retry_history": "",
        }

    domain = canonical_domain(url)
    polite_wait_domain(domain, per_domain_delay)

    session = get_session()

    result = check_url_with_retries(
        url=url,
        session=session,
        check_once=check_url_once,
        retry_cfg=retry_cfg,
        logger=None,
        check_once_kwargs={
            "timeout": timeout,
            "enable_soft_404": enable_soft_404,
            "enable_fingerprinting": enable_fingerprinting,
        },
    )

    return {
        "folder_path": folder_path,
        "title": title,
        "input_url": result.get("input_url", url),
        "final_url": result.get("final_url", ""),
        "status_code": result.get("status_code", ""),
        "ok": bool(result.get("ok", False)),
        "error_type": result.get("error_type", ""),
        "notes": result.get("notes", ""),
        "add_date": add_date,
        "retried": bool(result.get("retried", False)),
        "retry_count": int(result.get("retry_count", 0) or 0),
        "retry_history": result.get("retry_history", ""),
    }


# --------------------------------------------------
# CLI
# --------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Chrome bookmark links and write CSV + HTML outputs."
    )

    parser.add_argument(
        "--bookmarks",
        default=DEFAULT_BOOKMARKS_HTML,
        help="Path to bookmarks HTML export",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUTPUT_CSV,
        help="Output CSV path",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=DEFAULT_MAX_LINKS,
        help="0 = no limit",
    )

    parser.add_argument("--timeout-connect", type=int, default=DEFAULT_TIMEOUT_CONNECT)
    parser.add_argument("--timeout-read", type=int, default=DEFAULT_TIMEOUT_READ)

    parser.add_argument(
        "--enable-soft-404",
        action="store_true",
        default=DEFAULT_ENABLE_SOFT_404,
    )
    parser.add_argument(
        "--enable-fingerprinting",
        action="store_true",
        default=DEFAULT_ENABLE_FINGERPRINTING,
    )

    parser.add_argument(
        "--dedupe-mode",
        default=DEFAULT_DEDUPE_MODE,
        help="strict|basic|tracking_free|aggressive",
    )

    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--per-domain-delay", type=float, default=DEFAULT_PER_DOMAIN_DELAY_SEC)

    parser.add_argument(
        "--ignore-domain",
        action="append",
        default=list(DEFAULT_IGNORE_DOMAINS),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG, INFO, WARNING, ERROR",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="YAML config file path",
    )

    return parser


# --------------------------------------------------
# Main
# --------------------------------------------------
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config_path = Path(getattr(args, "config", "config.yaml"))
    yaml_config = load_yaml_config(config_path)
    cfg = build_config_from_args_and_yaml(args, yaml_config)

    setup_logging(cfg.log_level)

    logging.info(
        "Using config file: %s",
        config_path.resolve() if config_path.exists() else config_path,
    )
    logging.info(
        "FINAL SETTINGS: bookmarks=%s out=%s workers=%s per_domain_delay=%.2fs dedupe=%s soft404=%s fingerprint=%s ignores=%d",
        cfg.bookmarks,
        cfg.out,
        int(cfg.workers),
        float(cfg.per_domain_delay),
        cfg.dedupe_mode,
        cfg.enable_soft_404,
        cfg.enable_fingerprinting,
        len(cfg.ignore_domain),
    )

    html_path = Path(cfg.bookmarks)
    if not html_path.exists():
        raise FileNotFoundError(f"Bookmarks file not found: {html_path}")

    bookmarks = parse_bookmarks_html(html_path)
    logging.info("Parsed bookmarks: %d from %s", len(bookmarks), html_path)

    if bookmarks:
        sample_add = getattr(bookmarks[0], "add_date", None)
        if sample_add is None and isinstance(bookmarks[0], dict):
            sample_add = bookmarks[0].get("add_date")
        logging.info("Sample add_date: %s", sample_add)

    logging.info("TOTAL URLs in input (including duplicates): %d", len(bookmarks))

    dedupe_mode = (cfg.dedupe_mode or "strict").strip()
    bookmarks, dedupe_stats = dedupe_bookmarks_mod(bookmarks, mode=dedupe_mode)

    logging.info(
        "Dedupe mode: %s | Removed duplicates: %d | Remaining: %d",
        dedupe_stats.mode,
        dedupe_stats.duplicates,
        dedupe_stats.unique_out,
    )

    if cfg.max_links and cfg.max_links > 0:
        bookmarks = bookmarks[: int(cfg.max_links)]
        logging.info("Limiting to first %d bookmarks", len(bookmarks))

    out_path = Path(cfg.out)
    ensure_parent_dir(out_path)

    timeout = (int(cfg.timeout_connect), int(cfg.timeout_read))
    workers = max(1, int(cfg.workers))
    per_domain_delay = float(cfg.per_domain_delay)

    retry_cfg = RetryConfig(
        enabled=True,
        max_attempts=3,
        base_delay=2.0,
        backoff_multiplier=2.0,
        jitter=0.5,
    )

    fieldnames = [
        "folder_path",
        "title",
        "input_url",
        "final_url",
        "status_code",
        "ok",
        "error_type",
        "notes",
        "retried",
        "retry_count",
        "retry_history",
    ]

    valid_bookmarks: List[Bookmark] = []
    error_counts = Counter()
    fail_domain_counts = Counter()
    ok_count = 0
    total_processed = 0

    logging.info(
        "Parallel checking: workers=%d per_domain_delay=%.2fs soft_404=%s fingerprinting=%s retries=%s max_attempts=%d",
        workers,
        per_domain_delay,
        cfg.enable_soft_404,
        cfg.enable_fingerprinting,
        retry_cfg.enabled,
        retry_cfg.max_attempts,
    )

    with open(out_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        def process_one(bm: Any) -> Dict[str, Any]:
            return process_one_bookmark(
                bm=bm,
                ignore_domains=cfg.ignore_domain,
                timeout=timeout,
                enable_soft_404=cfg.enable_soft_404,
                enable_fingerprinting=cfg.enable_fingerprinting,
                per_domain_delay=per_domain_delay,
                retry_cfg=retry_cfg,
            )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(process_one, bm) for bm in bookmarks]

            for future in tqdm(as_completed(futures), total=len(futures), desc="Checking", unit="url"):
                try:
                    raw_row = future.result()
                except Exception:
                    logging.exception("Worker crashed while checking a URL")
                    raise

                row = CheckResult.from_worker_dict(raw_row)
                writer.writerow(row.to_csv_row())

                total_processed += 1

                if row.ok:
                    ok_count += 1

                    final_url = row.final_url or row.input_url
                    valid_bookmarks.append(
                        Bookmark(
                            title=row.title,
                            url=final_url,
                            folder_path=row.folder_path,
                            add_date=int(row.add_date or 0),
                        )
                    )
                else:
                    error_counts[row.error_type or "unknown_error"] += 1
                    fail_domain_counts[canonical_domain(row.final_url or row.input_url or "")] += 1

                if total_processed % 200 == 0:
                    csv_file.flush()

    logging.info(
        "Finished checks. total=%d ok=%d fail=%d",
        total_processed,
        ok_count,
        total_processed - ok_count,
    )

    valid_out, grouped_out, report_path = derive_output_paths(out_path)

    folder_preserving_out = out_path.with_name(
        f"{out_path.stem}_valid_preserve_folders.html"
    )

    write_chrome_bookmarks_html(valid_bookmarks, valid_out, "✅ Valid Links")
    logging.info(
        "Wrote valid bookmarks HTML: %s (valid=%d)",
        valid_out,
        len(valid_bookmarks),
    )

    write_valid_grouped_by_domain(
        valid_bookmarks,
        grouped_out,
        "✅ Valid Links (Grouped by Domain, Oldest First)",
    )
    logging.info(
        "Wrote grouped bookmarks HTML: %s (valid=%d)",
        grouped_out,
        len(valid_bookmarks),
    )

    write_folder_preserving_valid_bookmarks_html(
        bookmarks=valid_bookmarks,
        output_path=folder_preserving_out,
    )
    logging.info(
        "Wrote folder-preserving bookmarks HTML: %s (valid=%d)",
        folder_preserving_out,
        len(valid_bookmarks),
    )

    write_report_md(
        report_path,
        total_processed,
        ok_count,
        error_counts,
        fail_domain_counts,
    )
    logging.info("Wrote report: %s", report_path)


if __name__ == "__main__":
    main()