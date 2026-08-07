from __future__ import annotations

from pathlib import Path
import tempfile
import time

from app.core import database
from app.core.database import db, init_db, row
from app.services.usage_service import calculate_cost_micros, record_usage, require_model_balance, usage_logs
from app.utils.common import now


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
    assert calculate_cost_micros({"pricing_multiplier": 1, "unit_price": 0.2}, {}, quantity=3) == 600000


def test_official_and_user_logs() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "usage.db")
        try:
            init_db()
            stamp = now()
            with db() as conn:
                user_id = conn.execute(
                    "INSERT INTO users (created_at, updated_at, username, password, role, is_disabled, balance_micros) VALUES (?, ?, 'usage-user', 'x', 'user', 0, 20000)",
                    (stamp, stamp),
                ).lastrowid
                official_config_id = conn.execute(
                    """INSERT INTO model_configs
                    (created_at, updated_at, user_id, source, name, provider, encrypted_key, purpose, model_name, pricing_multiplier,
                     input_price_per_million, output_price_per_million, cache_read_price_per_million,
                     cache_write_price_per_million, unit_price, unit_name)
                    VALUES (?, ?, NULL, 'official', 'Official GPT', 'openai', 'x', 'script', 'gpt-test', 5, 1, 2, 0.1, 0.5, 0, 'token')""",
                    (stamp, stamp),
                ).lastrowid
                user_config_id = conn.execute(
                    """INSERT INTO model_configs
                    (created_at, updated_at, user_id, source, name, provider, encrypted_key, purpose, model_name, pricing_multiplier,
                     input_price_per_million, output_price_per_million, cache_read_price_per_million,
                     cache_write_price_per_million, unit_price, unit_name)
                    VALUES (?, ?, ?, 'user', 'Personal GPT', 'openai', 'x', 'script', 'gpt-user', 5, 1, 2, 0.1, 0.5, 0, 'token')""",
                    (stamp, stamp, user_id),
                ).lastrowid
            usage = {"inputTokens": 1000, "outputTokens": 500, "cacheReadTokens": 200, "cacheWriteTokens": 100}
            record_usage(
                int(user_id),
                {"source": "official", "officialConfigId": official_config_id, "provider": "openai", "model": "gpt-test"},
                "chat",
                time.monotonic(),
                usage,
            )
            record_usage(
                int(user_id),
                {"source": "user", "configId": user_config_id, "provider": "openai", "model": "gpt-user"},
                "chat",
                time.monotonic(),
                usage,
            )
            with db() as conn:
                result = usage_logs(conn, int(user_id))
                official_only = usage_logs(conn, int(user_id), source="official")
                user_only = usage_logs(conn, int(user_id), source="user")
            assert result["summary"]["calls"] == 2
            assert result["summary"]["costMicros"] == 17700
            assert official_only["summary"]["costMicros"] == 8850
            assert user_only["summary"]["costMicros"] == 8850
            assert official_only["summary"]["calls"] == 1
            assert user_only["summary"]["calls"] == 1
            assert {item["configName"] for item in result["logs"]} == {"Official GPT", "Personal GPT"}

            with db() as conn:
                assert row(conn, "SELECT balance_micros FROM users WHERE id=?", (user_id,))["balance_micros"] == 11150
                conn.execute("UPDATE users SET balance_micros=0 WHERE id=?", (user_id,))
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
            record_usage(
                int(user_id),
                {"source": "official", "officialConfigId": official_config_id, "provider": "openai", "model": "gpt-test"},
                "chat",
                time.monotonic(),
                usage,
            )
            with db() as conn:
                assert row(conn, "SELECT balance_micros FROM users WHERE id=?", (user_id,))["balance_micros"] == 0
                assert usage_logs(conn, int(user_id))["summary"]["costMicros"] == 26550
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_cost_calculation()
    test_official_and_user_logs()
