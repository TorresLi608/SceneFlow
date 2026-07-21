from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import sqlite3
import time
from typing import Any, Mapping

from fastapi import HTTPException

from app.core.database import db, row, rows
from app.utils.common import new_id, now


PRICE_FIELDS = {
    "pricingMultiplier": "pricing_multiplier",
    "inputPricePerMillion": "input_price_per_million",
    "outputPricePerMillion": "output_price_per_million",
    "cacheReadPricePerMillion": "cache_read_price_per_million",
    "cacheWritePricePerMillion": "cache_write_price_per_million",
    "unitPrice": "unit_price",
    "unitName": "unit_name",
}


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number) or number < 0:
        raise ValueError("pricing values must be finite and non-negative")
    return number


def normalize_pricing(payload: Mapping[str, Any], current: sqlite3.Row | None = None) -> dict[str, Any]:
    def value(api_key: str, db_key: str, default: Any) -> Any:
        if api_key in payload:
            return payload[api_key]
        if current is not None and db_key in current.keys():
            return current[db_key]
        return default

    unit_name = str(value("unitName", "unit_name", "token") or "token").strip().lower()
    if unit_name not in {"token", "request", "image", "second"}:
        raise ValueError("unitName must be token/request/image/second")
    multiplier = _number(value("pricingMultiplier", "pricing_multiplier", 1), 1)
    if multiplier <= 0:
        raise ValueError("pricingMultiplier must be greater than 0")
    return {
        "pricing_multiplier": multiplier,
        "input_price_per_million": _number(value("inputPricePerMillion", "input_price_per_million", 0), 0),
        "output_price_per_million": _number(value("outputPricePerMillion", "output_price_per_million", 0), 0),
        "cache_read_price_per_million": _number(value("cacheReadPricePerMillion", "cache_read_price_per_million", 0), 0),
        "cache_write_price_per_million": _number(value("cacheWritePricePerMillion", "cache_write_price_per_million", 0), 0),
        "unit_price": _number(value("unitPrice", "unit_price", 0), 0),
        "unit_name": unit_name,
    }


def pricing_updates(payload: Mapping[str, Any], current: sqlite3.Row) -> dict[str, Any]:
    pricing = normalize_pricing(payload, current)
    return {db_key: pricing[db_key] for api_key, db_key in PRICE_FIELDS.items() if api_key in payload}


def aggregate_token_usage(value: Mapping[str, Any] | None) -> dict[str, int]:
    result = {"inputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0, "cacheWriteTokens": 0}
    if not value:
        return result
    entries = [value] if "input_tokens" in value else [item for item in value.values() if isinstance(item, Mapping)]
    for usage in entries:
        details = usage.get("input_token_details") if isinstance(usage.get("input_token_details"), Mapping) else {}
        result["inputTokens"] += int(usage.get("input_tokens") or 0)
        result["outputTokens"] += int(usage.get("output_tokens") or 0)
        result["cacheReadTokens"] += int(details.get("cache_read") or 0)
        result["cacheWriteTokens"] += int(details.get("cache_creation") or 0)
    return result


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation:
        return Decimal(0)


def calculate_cost_micros(pricing: Mapping[str, Any], usage: Mapping[str, int], quantity: float = 0) -> int:
    input_tokens = max(0, int(usage.get("inputTokens") or 0))
    cache_read = max(0, int(usage.get("cacheReadTokens") or 0))
    cache_write = max(0, int(usage.get("cacheWriteTokens") or 0))
    uncached_input = max(0, input_tokens - cache_read - cache_write)
    token_cost = (
        _decimal(uncached_input) * _decimal(pricing.get("input_price_per_million"))
        + _decimal(usage.get("outputTokens")) * _decimal(pricing.get("output_price_per_million"))
        + _decimal(cache_read) * _decimal(pricing.get("cache_read_price_per_million"))
        + _decimal(cache_write) * _decimal(pricing.get("cache_write_price_per_million"))
    ) / Decimal(1_000_000)
    unit_cost = _decimal(quantity) * _decimal(pricing.get("unit_price"))
    cost = (token_cost + unit_cost) * _decimal(pricing.get("pricing_multiplier", 1))
    return int((cost * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def require_model_balance(conn: sqlite3.Connection, user_id: int, config: Mapping[str, Any]) -> None:
    source = str(config.get("source") or ("official" if config.get("officialConfigId") else "user"))
    if source != "official":
        return
    user = row(conn, "SELECT role, balance_micros FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
    if not user:
        raise HTTPException(401, "user not found")
    if (user["role"] or "user") != "superAdmin" and int(user["balance_micros"] or 0) <= 0:
        raise HTTPException(402, "当前余额不足，请先兑换额度后再使用官方模型。")


def record_usage(
    user_id: int,
    config: Mapping[str, Any],
    feature: str,
    started_at: float,
    usage: Mapping[str, int] | None = None,
    quantity: float = 0,
) -> None:
    token_usage = {"inputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0, "cacheWriteTokens": 0, **(usage or {})}
    source = str(config.get("source") or ("official" if config.get("officialConfigId") else "user"))
    config_id = config.get("officialConfigId") if source == "official" else config.get("configId")
    pricing = normalize_pricing({})
    if config_id:
        with db() as conn:
            stored_config = row(conn, "SELECT * FROM model_configs WHERE id=? AND source=?", (int(config_id), source))
        if stored_config:
            pricing = normalize_pricing({}, stored_config)
    cost_micros = calculate_cost_micros(pricing, token_usage, quantity)
    with db() as conn:
        conn.execute(
            """INSERT INTO usage_logs
            (id, created_at, user_id, feature, config_source, config_id, provider, model_name, duration_ms,
             input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, quantity, cost_micros,
             pricing_multiplier, input_price_per_million, output_price_per_million,
             cache_read_price_per_million, cache_write_price_per_million, unit_price, unit_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id("usage"),
                now(),
                user_id,
                feature[:40],
                source,
                int(config_id) if config_id else None,
                str(config.get("provider") or "")[:40],
                str(config.get("model") or "")[:160],
                max(0, int((time.monotonic() - started_at) * 1000)),
                token_usage["inputTokens"],
                token_usage["outputTokens"],
                token_usage["cacheReadTokens"],
                token_usage["cacheWriteTokens"],
                max(0, float(quantity)),
                cost_micros,
                pricing["pricing_multiplier"],
                pricing["input_price_per_million"],
                pricing["output_price_per_million"],
                pricing["cache_read_price_per_million"],
                pricing["cache_write_price_per_million"],
                pricing["unit_price"],
                pricing["unit_name"],
            ),
        )
        if source == "official" and cost_micros:
            conn.execute(
                "UPDATE users SET balance_micros=MAX(0, balance_micros-?), updated_at=? WHERE id=?",
                (cost_micros, now(), user_id),
            )


def usage_logs(conn: sqlite3.Connection, user_id: int, feature: str = "all", days: int = 30, source: str = "all") -> dict[str, Any]:
    conditions = ["user_id=?", "created_at>=datetime('now', ?)"]
    args: list[Any] = [user_id, f"-{max(1, min(days, 365))} days"]
    if feature != "all":
        conditions.append("feature=?")
        args.append(feature)
    if source != "all":
        conditions.append("config_source=?")
        args.append(source)
    where = " AND ".join(conditions)
    items = rows(conn, f"SELECT * FROM usage_logs WHERE {where} ORDER BY created_at DESC LIMIT 500", tuple(args))
    summary = row(
        conn,
        f"""SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens,
        COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(cost_micros),0) AS cost_micros
        FROM usage_logs WHERE {where}""",
        tuple(args),
    )
    return {
        "summary": {
            "calls": summary["calls"],
            "inputTokens": summary["input_tokens"],
            "outputTokens": summary["output_tokens"],
            "costMicros": summary["cost_micros"],
        },
        "logs": [usage_log_json(item) for item in items],
    }


def usage_log_json(item: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": item["id"],
        "createdAt": item["created_at"],
        "feature": item["feature"],
        "source": item["config_source"],
        "provider": item["provider"],
        "model": item["model_name"],
        "durationMs": item["duration_ms"],
        "inputTokens": item["input_tokens"],
        "outputTokens": item["output_tokens"],
        "cacheReadTokens": item["cache_read_tokens"],
        "cacheWriteTokens": item["cache_write_tokens"],
        "quantity": item["quantity"],
        "costMicros": item["cost_micros"],
        "pricingMultiplier": item["pricing_multiplier"],
        "inputPricePerMillion": item["input_price_per_million"],
        "outputPricePerMillion": item["output_price_per_million"],
        "cacheReadPricePerMillion": item["cache_read_price_per_million"],
        "cacheWritePricePerMillion": item["cache_write_price_per_million"],
        "unitPrice": item["unit_price"],
        "unitName": item["unit_name"],
    }
