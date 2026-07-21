from __future__ import annotations

from pathlib import Path
import tempfile
import time

import database
from database import db, init_db
from services.usage_service import calculate_cost_micros, record_usage, require_model_balance, usage_logs
from lib.utils import now


def test_cost_calculation() -> None:
    pricing = {
        "pricing_multiplier": 5,
        "input_price_per_million": 1,
        "output_price_per_million": 2,
        "cache_read_price_per_million": 0.1,
        "cache_write_price_per_million": 0.5,
        "unit_price": 0,
    }
    usage = {"inputTokens": 1000, "outputTokens": 500, "cacheReadTokens": 200, "cacheWriteTokens": 100}
    assert calculate_cost_micros(pricing, usage) == 8850


def test_official_and_user_logs() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "usage.db")
        try:
            init_db()
            stamp = now()
            with db() as conn:
                user_id = conn.execute(
                    "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled) VALUES (?, ?, 'usage-user', 'x', 'user', 0)",
                    (stamp, stamp),
                ).lastrowid
                config_id = conn.execute(
                    """INSERT INTO official_model_configs
                    (created_at, updated_at, provider, encrypted_key, purpose, model_name, pricing_multiplier,
                     input_price_per_million, output_price_per_million, cache_read_price_per_million,
                     cache_write_price_per_million, unit_price, unit_name)
                    VALUES (?, ?, 'openai', 'x', 'script', 'gpt-test', 5, 1, 2, 0.1, 0.5, 0, 'token')""",
                    (stamp, stamp),
                ).lastrowid
            usage = {"inputTokens": 1000, "outputTokens": 500, "cacheReadTokens": 200, "cacheWriteTokens": 100}
            record_usage(
                int(user_id),
                {"source": "official", "officialConfigId": config_id, "provider": "openai", "model": "gpt-test"},
                "chat",
                time.monotonic(),
                usage,
            )
            record_usage(
                int(user_id),
                {"source": "user", "configId": 9, "provider": "openai", "model": "gpt-user"},
                "chat",
                time.monotonic(),
                usage,
            )
            with db() as conn:
                result = usage_logs(conn, int(user_id))
                official_only = usage_logs(conn, int(user_id), source="official")
                user_only = usage_logs(conn, int(user_id), source="user")
            assert result["summary"]["calls"] == 2
            assert result["summary"]["costMicros"] == 8850
            assert result["logs"][0]["costMicros"] == 0
            assert result["logs"][1]["costMicros"] == 8850
            assert official_only["summary"]["calls"] == 1
            assert user_only["summary"]["calls"] == 1

            with db() as conn:
                try:
                    require_model_balance(conn, int(user_id), {"source": "official"})
                    raise AssertionError("zero-balance ordinary users must be blocked from official configs")
                except Exception as exc:
                    assert getattr(exc, "status_code", None) == 402
                    assert "余额不足" in str(getattr(exc, "detail", ""))
                require_model_balance(conn, int(user_id), {"source": "user"})
                conn.execute("UPDATE users SET balance_micros=1 WHERE id=?", (user_id,))
                require_model_balance(conn, int(user_id), {"source": "official"})
                conn.execute("UPDATE users SET role='superAdmin', balance_micros=0 WHERE id=?", (user_id,))
                require_model_balance(conn, int(user_id), {"source": "official"})
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_cost_calculation()
    test_official_and_user_logs()
