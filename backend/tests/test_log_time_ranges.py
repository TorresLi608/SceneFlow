from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select

from app.api.v1 import admin, usage
from app.core import database
from app.core.database import db, init_db
from app.core.security import token_for
from app.models import ErrorLog, UsageLog, User
from app.services.error_log_service import find_error_logs
from app.utils.common import now


def test_log_time_ranges() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "log-ranges.db"
        try:
            init_db()
            with db() as session:
                stamp = now()
                user = User(created_at=stamp, updated_at=stamp, username="range-user", password="x")
                session.add(user)
                session.flush()
                user_id = int(user.id)
                admin_id = int(session.exec(select(User).where(User.role == "superAdmin")).one().id)
                # A local UTC+8 day, deliberately older than the legacy days filter.
                timestamps = {
                    "before": "2024-12-31T15:59:59.999999+00:00",
                    "start": "2024-12-31T16:00:00+00:00",
                    "noon": "2025-01-01T04:05:06+00:00",
                    "end": "2025-01-01T15:59:59+00:00",
                    "fraction": "2025-01-01T15:59:59.999999+00:00",
                    "after": "2025-01-01T16:00:00+00:00",
                }
                for name, created_at in timestamps.items():
                    session.add(UsageLog(
                        id=f"usage_{name}", created_at=created_at, user_id=user_id,
                        feature="image" if name == "fraction" else "chat",
                        config_source="user" if name == "fraction" else "official",
                        input_tokens=10, output_tokens=20, cost_micros=3,
                    ))
                    session.add(ErrorLog(
                        id=f"error_{name}", created_at=created_at, user_id=user_id,
                        request_id=f"request_{name}", method="POST", route="/api/range-case",
                        status_code=502, error_code="RANGE_TEST", message="range-case",
                    ))
                session.add(UsageLog(
                    id="usage_other_user", created_at=timestamps["noon"], user_id=admin_id,
                    feature="chat", config_source="official", cost_micros=99999,
                ))

            app = FastAPI()
            app.include_router(admin.router)
            app.include_router(usage.router)
            user_headers = {"Authorization": f"Bearer {token_for(user_id)}"}
            admin_headers = {"Authorization": f"Bearer {token_for(admin_id)}"}
            time_range = {"startTime": "2025-01-01T00:00:00+08:00", "endTime": "2025-01-01T23:59:59+08:00"}
            with TestClient(app) as client:
                response = client.get("/api/usage/logs", params={**time_range, "days": 1}, headers=user_headers)
                assert response.status_code == 200, response.text
                result = response.json()
                assert {item["id"] for item in result["logs"]} == {"usage_start", "usage_noon", "usage_end", "usage_fraction"}
                assert result["summary"] == {"calls": 4, "inputTokens": 40, "outputTokens": 80, "costMicros": "12"}
                filtered = client.get("/api/usage/logs", params={**time_range, "feature": "image", "source": "user"}, headers=user_headers)
                assert filtered.status_code == 200, filtered.text
                assert filtered.json()["summary"]["calls"] == 1
                assert filtered.json()["logs"][0]["id"] == "usage_fraction"

                endpoints = [
                    ("/api/usage/logs", "logs", user_headers, {}),
                    ("/api/admin/usage-logs", "usageLogs", admin_headers, {"search": "range-user"}),
                    ("/api/admin/error-logs", "errorLogs", admin_headers, {"search": "range-case", "errorCode": "RANGE_TEST"}),
                ]
                for path, collection, headers, filters in endpoints:
                    response = client.get(path, params={**time_range, **filters}, headers=headers)
                    assert response.status_code == 200, response.text
                    assert len(response.json()[collection]) == 4
                    utc_range = {"startTime": "2024-12-31T16:00:00Z", "endTime": "2025-01-01T15:59:59Z"}
                    equivalent = client.get(path, params={**utc_range, **filters}, headers=headers)
                    assert equivalent.status_code == 200, equivalent.text
                    assert equivalent.json() == response.json()

                    if "pagination" in response.json():
                        paged = client.get(path, params={**time_range, **filters, "pageSize": 2, "page": 2}, headers=headers)
                        assert paged.status_code == 200, paged.text
                        assert paged.json()["pagination"] == {"total": 4, "page": 2, "pageSize": 2, "pageCount": 2}
                        assert len(paged.json()[collection]) == 2

                    second = {"startTime": time_range["endTime"], "endTime": time_range["endTime"]}
                    response = client.get(path, params={**second, **filters}, headers=headers)
                    assert response.status_code == 200, response.text
                    assert {item["id"].split("_", 1)[1] for item in response.json()[collection]} == {"end", "fraction"}
                    empty = client.get(path, params={"startTime": "2025-02-01T00:00:00Z", "endTime": "2025-02-01T23:59:59Z"}, headers=headers)
                    assert empty.status_code == 200, empty.text
                    assert empty.json()[collection] == []

                    for invalid in (
                        {"startTime": time_range["startTime"]},
                        {"endTime": time_range["endTime"]},
                        {"startTime": time_range["endTime"], "endTime": time_range["startTime"]},
                        {**time_range, "startTime": "invalid"},
                        {**time_range, "startTime": "2025-01-01T00:00:00"},
                        {**time_range, "endTime": "9999-12-31T23:59:59Z"},
                    ):
                        rejected = client.get(path, params=invalid, headers=headers)
                        assert rejected.status_code == 422, (path, invalid, rejected.text)

                assert client.get("/api/admin/usage-logs", params=time_range, headers=user_headers).status_code == 403
                assert client.get("/api/admin/error-logs", params=time_range, headers=user_headers).status_code == 403
                assert client.get("/api/usage/logs", params=time_range).status_code == 401

            # The diagnostic chat tool still searches all history when no range is supplied.
            with db() as session:
                total, _ = find_error_logs(session, search="range-case")
                assert total == 6
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_log_time_ranges()
