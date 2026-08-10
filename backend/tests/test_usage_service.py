from __future__ import annotations

from pathlib import Path
import tempfile
import time

from sqlmodel import select

from app.core import database
from app.core.database import db, init_db
from app.models import ModelConfig, User
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
            with db() as session:
                user = User(
                    created_at=stamp,
                    updated_at=stamp,
                    username="usage-user",
                    password="x",
                    role="user",
                    is_disabled=False,
                    balance_micros=20000,
                )
                session.add(user)
                session.flush()
                user_id = user.id
                official_config = ModelConfig(
                    created_at=stamp, updated_at=stamp, user_id=None, source="official", name="Official GPT",
                    provider="openai", encrypted_key="x", purpose="script", model_name="gpt-test",
                    pricing_multiplier=5, input_price_per_million=1, output_price_per_million=2,
                    cache_read_price_per_million=0.1, cache_write_price_per_million=0.5, unit_price=0, unit_name="token",
                )
                user_config = ModelConfig(
                    created_at=stamp, updated_at=stamp, user_id=user_id, source="user", name="Personal GPT",
                    provider="openai", encrypted_key="x", purpose="script", model_name="gpt-user",
                    pricing_multiplier=5, input_price_per_million=1, output_price_per_million=2,
                    cache_read_price_per_million=0.1, cache_write_price_per_million=0.5, unit_price=0, unit_name="token",
                )
                session.add_all([official_config, user_config])
                session.flush()
                official_config_id, user_config_id = official_config.id, user_config.id
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
            with db() as session:
                result = usage_logs(session, int(user_id))
                official_only = usage_logs(session, int(user_id), source="official")
                user_only = usage_logs(session, int(user_id), source="user")
            assert result["summary"]["calls"] == 2
            assert result["summary"]["costMicros"] == "17700"
            assert official_only["summary"]["costMicros"] == "8850"
            assert user_only["summary"]["costMicros"] == "8850"
            assert official_only["summary"]["calls"] == 1
            assert user_only["summary"]["calls"] == 1
            assert {item["configName"] for item in result["logs"]} == {"Official GPT", "Personal GPT"}

            with db() as session:
                saved = session.exec(select(User).where(User.id == user_id)).one()
                assert saved.balance_micros == 11150
                saved.balance_micros = 0
                session.flush()
                try:
                    require_model_balance(session, int(user_id), {"source": "official"})
                    raise AssertionError("zero-balance ordinary users must be blocked from official configs")
                except Exception as exc:
                    assert getattr(exc, "status_code", None) == 402
                    assert "余额不足" in str(getattr(exc, "detail", ""))
                require_model_balance(session, int(user_id), {"source": "user"})
                saved.balance_micros = 1
                session.flush()
                require_model_balance(session, int(user_id), {"source": "official"})
                saved.role = "superAdmin"
                saved.balance_micros = 0
                session.flush()
                require_model_balance(session, int(user_id), {"source": "official"})
            record_usage(
                int(user_id),
                {"source": "official", "officialConfigId": official_config_id, "provider": "openai", "model": "gpt-test"},
                "chat",
                time.monotonic(),
                usage,
            )
            with db() as session:
                assert session.exec(select(User.balance_micros).where(User.id == user_id)).one() == 0
                assert usage_logs(session, int(user_id))["summary"]["costMicros"] == "26550"
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_cost_calculation()
    test_official_and_user_logs()
