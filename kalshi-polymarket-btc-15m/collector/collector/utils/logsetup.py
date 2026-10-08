"""Logging setup."""

import logging


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger once; later calls keep the first configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
