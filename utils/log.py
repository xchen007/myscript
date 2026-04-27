"""Shared loguru configuration."""

from __future__ import annotations

import sys

from loguru import logger


def setup_logging(
    verbose: bool = False,
    fmt: str = (
        "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}"
    ),
    colorize: bool = True,
) -> None:
    """Remove existing loguru handlers and add a single stderr handler.

    Args:
        verbose: Use DEBUG level when True, INFO otherwise.
        fmt: Loguru format string.
        colorize: Enable ANSI colour codes.
    """
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format=fmt, colorize=colorize)
