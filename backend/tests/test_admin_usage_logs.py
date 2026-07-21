from __future__ import annotations

from pathlib import Path
import tempfile
import time

from app.api.v1.admin import list_all_usage_logs
from app.core import database
from app.core.database import db, init_db
from app.services.usage_service import record_usage
from app.utils.common import now


def test_admin_usage_logs_support_username_search_and_pagination() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "admin-usage.db"
        try:
            init_db()
            stamp = now()
            with db() as conn:
                alice_id = int(conn.execute("INSERT INTO users (created_at, updated_at, username, password, role) VALUES (?, ?, 'alice', 'x', 'user')", (stamp, stamp)).lastrowid)
                bob_id = int(conn.execute("INSERT INTO users (created_at, updated_at, username, password, role) VALUES (?, ?, 'bob', 'x', 'user')", (stamp, stamp)).lastrowid)
            config = {"source": "user", "provider": "openai", "model": "personal-model"}
            record_usage(alice_id, config, "chat", time.monotonic(), {"inputTokens": 10, "outputTokens": 5})
            record_usage(bob_id, config, "chat", time.monotonic(), {"inputTokens": 20, "outputTokens": 10})

            result = list_all_usage_logs(1, search="lic", page=1, page_size=10)
            assert result["pagination"]["total"] == 1
            assert result["usageLogs"][0]["user"]["username"] == "alice"
            assert result["usageLogs"][0]["inputTokens"] == 10

            paged = list_all_usage_logs(1, page=2, page_size=1)
            assert paged["pagination"]["total"] == 2
            assert len(paged["usageLogs"]) == 1
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_admin_usage_logs_support_username_search_and_pagination()
