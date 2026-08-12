from __future__ import annotations

import logging

from app.core.config import LOG_LEVEL


def configure_logging() -> None:
    """Attach a single stream handler at startup.

    `force=True` replaces whatever uvicorn installed so application records and access logs
    share one format instead of appearing twice.
    """
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
