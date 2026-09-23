"""Logging to stderr: the portal forwards it to the journal (`journalctl --user -u xdg-desktop-portal-wlr`)."""

import logging
import os

NAME = "compartir-selector"


def configure(debug: bool = False) -> logging.Logger:
    """Configure the program's root logger once. With debug (or COMPARTIR_SELECTOR_DEBUG=1) the level is DEBUG."""
    level = logging.DEBUG if debug or os.environ.get("COMPARTIR_SELECTOR_DEBUG") == "1" else logging.INFO
    logger = logging.getLogger(NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()  # stderr
        handler.setFormatter(logging.Formatter(f"{NAME}: %(levelname)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def get(module: str) -> logging.Logger:
    return logging.getLogger(f"{NAME}.{module}")
