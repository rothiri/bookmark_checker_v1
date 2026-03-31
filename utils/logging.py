from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    """
    Configure application-wide logging.

    This should be called once at startup (in main.py).
    All modules then share the same logger configuration.

    Example:
        setup_logging("DEBUG")
    """
    numeric = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
