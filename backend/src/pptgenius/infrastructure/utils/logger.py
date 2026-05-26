"""Structured logging with ANSI-colored console and rotating file output.

Configured via ``LogConfig`` in config.yaml / config.local.yaml.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# -- ANSI color codes -------------------------------------------------------
_RESET = "\033[0m"
_COLORS = {
    logging.DEBUG:    "\033[36m",    # cyan
    logging.INFO:     "\033[32m",    # green
    logging.WARNING:  "\033[33m",    # yellow
    logging.ERROR:    "\033[31m",    # red
    logging.CRITICAL: "\033[41m",    # red bg
}
_LEVEL_NAME = {
    logging.DEBUG:    "DEBUG",
    logging.INFO:     "INFO ",
    logging.WARNING:  "WARN ",
    logging.ERROR:    "ERROR",
    logging.CRITICAL: "FATAL",
}


class _ColoredFormatter(logging.Formatter):
    """ANSI-colored console formatter. Restores original record attrs after format."""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelno, "")
        if color:
            orig_levelname = record.levelname
            orig_name = record.name
            record.levelname = f"{color}{_LEVEL_NAME.get(record.levelno, orig_levelname)}{_RESET}"
            record.name = f"\033[1m{orig_name}{_RESET}"
            try:
                return super().format(record)
            finally:
                record.levelname = orig_levelname
                record.name = orig_name
        return super().format(record)


# -- public API -------------------------------------------------------------

def setup_logging(
    level: str = "INFO",
    fmt: str = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
    file_enabled: bool = True,
    file_path: str = "logs/app.log",
    file_max_bytes: int = 10 * 1024 * 1024,
    file_backup_count: int = 5,
) -> None:
    """Configure root logger with colored console + rotating file handler.

    Safe to call multiple times — duplicates are cleared first.
    """
    root = logging.getLogger()
    root.setLevel(_resolve_level(level))
    root.handlers.clear()

    # Console — colored
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(root.level)
    ch.setFormatter(_ColoredFormatter(fmt, datefmt))
    root.addHandler(ch)

    # File — rotating
    if file_enabled:
        fp = Path(file_path)
        if fp.parent and not fp.parent.exists():
            fp.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            str(fp), maxBytes=file_max_bytes, backupCount=file_backup_count, encoding="utf-8"
        )
        fh.setLevel(root.level)
        fh.setFormatter(logging.Formatter(fmt, datefmt))
        root.addHandler(fh)


def setup_logging_from_config() -> None:
    """Convenience: read ``Settings().log`` and call :func:`setup_logging`."""
    from pptgenius.infrastructure.config import get_settings

    cfg = get_settings().log
    setup_logging(
        level=cfg.level,
        fmt=cfg.fmt,
        datefmt=cfg.datefmt,
        file_enabled=cfg.file_enabled,
        file_path=cfg.file_path,
        file_max_bytes=cfg.file_max_bytes,
        file_backup_count=cfg.file_backup_count,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a child logger for *name* (typically ``__name__``)."""
    return logging.getLogger(name)


def _resolve_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO)
