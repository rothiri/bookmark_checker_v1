from __future__ import annotations

from pathlib import Path
from typing import Tuple


def ensure_parent_dir(path: Path) -> None:
    """
    Ensure the parent directory for a file path exists.
    Safe to call multiple times.
    """
    path.parent.mkdir(parents=True, exist_ok=True)


def derive_output_paths(base_csv_path: Path) -> Tuple[Path, Path, Path]:
    """
    Given the main CSV output path, derive all related outputs.

    Example:
        input:
            bookmark_link_check_results.csv

        output:
            - bookmark_link_check_results.valid.html
            - bookmark_link_check_results.valid.grouped_by_domain.oldest_first.html
            - bookmark_link_check_results.report.md
    """
    valid_html = base_csv_path.with_suffix(".valid.html")
    grouped_html = base_csv_path.with_suffix(".valid.grouped_by_domain.oldest_first.html")
    report_md = base_csv_path.with_suffix(".report.md")

    return valid_html, grouped_html, report_md
