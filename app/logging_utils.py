from __future__ import annotations

import logging
from pathlib import Path

from .security import redact_sensitive


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive(super().format(record))


def setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("chatgpt_media_downloader")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = RedactingFormatter("%(asctime)s | %(levelname)s | %(message)s")

    if not logger.handlers:
        handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    download_logger = logging.getLogger("chatgpt_media_downloader.download")
    download_logger.setLevel(logging.INFO)
    download_logger.propagate = False
    if not download_logger.handlers:
        handler = logging.FileHandler(log_dir / "downloads.log", encoding="utf-8")
        handler.setFormatter(formatter)
        download_logger.addHandler(handler)
    return logger
