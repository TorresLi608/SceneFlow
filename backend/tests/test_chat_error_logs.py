from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlmodel import select

from app.api.v1 import admin, chat
from app.core import database
from app.core.database import db, init_db
from app.core.security import token_for
from app.main import http_exception_handler
from app.models import ChatMessage, User
from app.services.error_log_service import find_error_logs, record_http_error, safe_error_reason
from app.utils.common import now


CAUSE = "`temperature` is not supported for claude-fable-5 at non-default values."
PRIVATE = "sk-secret private-chat https://provider.test/file?signature=private"


def test_safe_error_facts() -> None:
    assert safe_error_reason(ValueError(f"{PRIVATE}: {CAUSE}; model output: {PRIVATE}")) == CAUSE
    request = httpx.Request("POST", "https://provider.test")
    assert safe_error_reason(httpx.ReadTimeout(PRIVATE, request=request)) == "upstream request timed out"
    assert safe_error_reason(httpx.ConnectError(PRIVATE, request=request)) == "upstream connection failed"
    error = httpx.HTTPStatusError(PRIVATE, request=request, response=httpx.Response(429))
    assert safe_error_reason(error) == "upstream request failed (HTTP 429)"
    from openai import BadRequestError
    error = BadRequestError(PRIVATE, response=httpx.Response(400, request=request), body={"private": PRIVATE})
    assert safe_error_reason(error) == "upstream request failed (HTTP 400)"
    wrapper = HTTPException(502, f"failed to chat: {PRIVATE}")
    wrapper.__cause__ = error
    assert safe_error_reason(wrapper) == "upstream request failed (HTTP 400)"
    wrapper.__cause__ = ValueError(PRIVATE)
    assert safe_error_reason(wrapper) == "ValueError"
    assert safe_error_reason(RuntimeError("Recursion limit of 12 reached without hitting a stop condition " + PRIVATE)) == "Agent step limit reached (12)"
    wrapper.__cause__ = wrapper
    assert safe_error_reason(wrapper) == "HTTPException"


def test_chat_stream_and_http_logs_keep_redacted_cause() -> None:
    original = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "chat-errors.db"
        try:
            init_db()
            with db() as session:
                user_id = int(session.exec(select(User).where(User.role == "superAdmin")).one().id)
            app = FastAPI()
            app.include_router(chat.router)
            app.include_router(admin.router)
            app.add_exception_handler(HTTPException, http_exception_handler)
            request_ids = []

            @app.middleware("http")
            async def request_id(request, call_next):
                request.state.request_id = f"req_test_{len(request_ids)}"
                request_ids.append(request.state.request_id)
                return await call_next(request)

            async def context(*args):
                yield {"type": "context_ready", "messages": [{"role": "user", "content": "test"}]}

            async def stream_error(*args):
                raise ValueError(f"{CAUSE} {PRIVATE}")
                yield  # Make this a stream even though the first operation raises.

            message = ChatMessage(id="test-message", session_id="test-chat", role="user", content="test", created_at=now())
            config = {"provider": "anthropic", "model": "claude-fable-5"}
            with (
                patch.object(chat, "begin_chat_turn", return_value=(config, message)),
                patch.object(chat, "prepare_chat_turn", new=AsyncMock(return_value=(config, message, []))),
                patch.object(chat, "_image_config", return_value=None),
                patch.object(chat, "stream_context_messages", new=context),
                patch.object(chat, "stream_chat_agent", new=stream_error),
                patch.object(chat, "run_chat_agent", new=AsyncMock(side_effect=ValueError(f"{CAUSE} {PRIVATE}"))),
                TestClient(app) as client,
            ):
                headers = {"Authorization": f"Bearer {token_for(user_id)}"}
                response = client.post("/api/chat/sessions/test-chat/messages/stream", json={"content": "test"}, headers=headers)
                assert response.status_code == 200
                assert CAUSE in [json.loads(line) for line in response.text.splitlines()][-1]["error"]
                stream_id = request_ids[-1]
                response = client.post("/api/chat/sessions/test-chat/messages", json={"content": "test"}, headers=headers)
                assert response.status_code == 502 and CAUSE in response.json()["error"]
                http_id = request_ids[-1]
                for request_id, code in ((stream_id, "CHAT_STREAM_FAILED"), (http_id, "PROVIDER_FAILURE")):
                    result = client.get("/api/admin/error-logs", params={"requestId": request_id}, headers=headers)
                    assert result.status_code == 200, result.text
                    rows = result.json()["errorLogs"]
                    assert len(rows) == 1, rows
                    assert rows[0]["message"] == f"failed to chat: {CAUSE}", rows
                    assert rows[0]["statusCode"] == 502 and rows[0]["errorCode"] == code
                    assert "sk-secret" not in result.text and "signature=" not in result.text

            # Logging failure must not mask the original chat error.
            class BrokenError(Exception):
                def __str__(self):
                    raise RuntimeError("broken formatter")

            request = Request({"type": "http", "method": "POST", "path": "/test", "headers": []})
            request.state.request_id = "req_broken"
            with patch("app.services.error_log_service.logger.exception") as warning:
                record_http_error(request, 502, "failed to chat", exception=BrokenError())
                warning.assert_called_once()
            with db() as session:
                assert find_error_logs(session, request_id="req_broken")[0] == 0
        finally:
            database.DB_PATH = original


if __name__ == "__main__":
    test_safe_error_facts()
    test_chat_stream_and_http_logs_keep_redacted_cause()
