"""Central logging setup for rootmltool modules."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure package-wide logging.

    TODO: Extend with structured JSON logging when integrated into orchestrated pipelines.
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
