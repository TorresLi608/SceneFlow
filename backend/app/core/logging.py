from __future__ import annotations

from contextvars import ContextVar, Token
import logging

from app.core.config import LOG_LEVEL


_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def set_request_id(value: str) -> Token[str]:
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def configure_logging() -> None:
    """Attach a single stream handler at startup.

    `force=True` replaces whatever uvicorn installed so application records and access logs
    share one format instead of appearing twice.
    """
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s request=%(request_id)s %(message)s",
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())
