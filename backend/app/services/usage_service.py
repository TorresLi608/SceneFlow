from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import time
from typing import Any, Mapping

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.core.database import db
from app.models import ModelConfig, UsageLog, User
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


def _number(value: Any, default: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        number = Decimal(default)
    if not number.is_finite() or number < 0:
        raise ValueError("pricing values must be finite and non-negative")
    return format(number, "f")


def pricing_snapshot(pricing: Mapping[str, Any]) -> str:
    return json.dumps(dict(pricing), ensure_ascii=False, separators=(",", ":"))


def normalize_pricing(payload: Mapping[str, Any], current: ModelConfig | UsageLog | None = None) -> dict[str, Any]:
    stored: Mapping[str, Any] = {}
    if current is not None and current.pricing_json:
        try:
            parsed = json.loads(current.pricing_json)
            stored = parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            stored = {}

    def value(api_key: str, db_key: str, default: Any) -> Any:
        if api_key in payload:
            return payload[api_key]
        if db_key in stored:
            return stored[db_key]
        if current is not None and hasattr(current, db_key):
            return getattr(current, db_key)
        return default

    unit_name = str(value("unitName", "unit_name", "token") or "token").strip().lower()
    if unit_name not in {"token", "request", "image", "second"}:
        raise ValueError("unitName must be token/request/image/second")
    multiplier = _number(value("pricingMultiplier", "pricing_multiplier", 1), "1")
    if Decimal(multiplier) <= 0:
        raise ValueError("pricingMultiplier must be greater than 0")
    return {
        "pricing_multiplier": multiplier,
        "input_price_per_million": _number(value("inputPricePerMillion", "input_price_per_million", 0), "0"),
        "output_price_per_million": _number(value("outputPricePerMillion", "output_price_per_million", 0), "0"),
        "cache_read_price_per_million": _number(value("cacheReadPricePerMillion", "cache_read_price_per_million", 0), "0"),
        "cache_write_price_per_million": _number(value("cacheWritePricePerMillion", "cache_write_price_per_million", 0), "0"),
        "unit_price": _number(value("unitPrice", "unit_price", 0), "0"),
        "unit_name": unit_name,
    }


def pricing_updates(payload: Mapping[str, Any], current: ModelConfig) -> dict[str, Any]:
    pricing = normalize_pricing(payload, current)
    updates = {db_key: pricing[db_key] for api_key, db_key in PRICE_FIELDS.items() if api_key in payload}
    if updates:
        updates["pricing_json"] = pricing_snapshot(pricing)
    return updates


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


def require_model_balance(session: Session, user_id: int, config: Mapping[str, Any]) -> None:
    source = str(config.get("source") or ("official" if config.get("officialConfigId") else "user"))
    if source != "official":
        return
    user = session.exec(select(User).where(User.id == user_id, User.deleted_at.is_(None))).first()
    if not user:
        raise HTTPException(401, "user not found")
    if (user.role or "user") != "superAdmin" and int(user.balance_micros or 0) <= 0:
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
        with db() as session:
            stored_config = session.exec(
                select(ModelConfig).where(ModelConfig.id == int(config_id), ModelConfig.source == source)
            ).first()
        if stored_config:
            pricing = normalize_pricing({}, stored_config)
    cost_micros = calculate_cost_micros(pricing, token_usage, quantity)
    with db() as session:
        session.add(
            UsageLog(
                id=new_id("usage"),
                created_at=now(),
                user_id=user_id,
                feature=feature[:40],
                config_source=source,
                config_id=int(config_id) if config_id else None,
                provider=str(config.get("provider") or "")[:40],
                model_name=str(config.get("model") or "")[:160],
                duration_ms=max(0, int((time.monotonic() - started_at) * 1000)),
                input_tokens=token_usage["inputTokens"],
                output_tokens=token_usage["outputTokens"],
                cache_read_tokens=token_usage["cacheReadTokens"],
                cache_write_tokens=token_usage["cacheWriteTokens"],
                quantity=max(0, float(quantity)),
                cost_micros=cost_micros,
                pricing_multiplier=pricing["pricing_multiplier"],
                input_price_per_million=pricing["input_price_per_million"],
                output_price_per_million=pricing["output_price_per_million"],
                cache_read_price_per_million=pricing["cache_read_price_per_million"],
                cache_write_price_per_million=pricing["cache_write_price_per_million"],
                unit_price=pricing["unit_price"],
                unit_name=pricing["unit_name"],
                pricing_json=pricing_snapshot(pricing),
            )
        )
        if source == "official" and cost_micros:
            # Kept as a SQL-side atomic decrement so concurrent requests cannot clobber each other.
            session.execute(
                update(User)
                .where(User.id == user_id, User.role != "superAdmin")
                .values(balance_micros=func.max(0, User.balance_micros - cost_micros), updated_at=now())
                .execution_options(synchronize_session=False)
            )


def usage_logs(session: Session, user_id: int, feature: str = "all", days: int = 30, source: str = "all") -> dict[str, Any]:
    conditions = [
        UsageLog.user_id == user_id,
        UsageLog.created_at >= func.datetime("now", f"-{max(1, min(days, 365))} days"),
    ]
    if feature != "all":
        conditions.append(UsageLog.feature == feature)
    if source != "all":
        conditions.append(UsageLog.config_source == source)
    items = session.exec(
        select(UsageLog, ModelConfig.name)
        .join(
            ModelConfig,
            (ModelConfig.id == UsageLog.config_id) & (ModelConfig.source == UsageLog.config_source),
            isouter=True,
        )
        .where(*conditions)
        .order_by(UsageLog.created_at.desc())
        .limit(500)
    ).all()
    calls, input_tokens, output_tokens, cost_micros = session.exec(
        select(
            func.count(),
            func.coalesce(func.sum(UsageLog.input_tokens), 0),
            func.coalesce(func.sum(UsageLog.output_tokens), 0),
            func.coalesce(func.sum(UsageLog.cost_micros), 0),
        )
        .select_from(UsageLog)
        .where(*conditions)
    ).one()
    return {
        "summary": {
            "calls": calls,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "costMicros": str(cost_micros),
        },
        "logs": [usage_log_json(item, config_name) for item, config_name in items],
    }


def usage_log_json(item: UsageLog, config_name: str | None = "") -> dict[str, Any]:
    pricing = normalize_pricing({}, item)
    return {
        "id": item.id,
        "createdAt": item.created_at,
        "feature": item.feature,
        "source": item.config_source,
        "provider": item.provider,
        "configName": config_name or "",
        "model": item.model_name,
        "durationMs": item.duration_ms,
        "inputTokens": item.input_tokens,
        "outputTokens": item.output_tokens,
        "cacheReadTokens": item.cache_read_tokens,
        "cacheWriteTokens": item.cache_write_tokens,
        "quantity": item.quantity,
        "costMicros": str(item.cost_micros),
        "pricingMultiplier": pricing["pricing_multiplier"],
        "inputPricePerMillion": pricing["input_price_per_million"],
        "outputPricePerMillion": pricing["output_price_per_million"],
        "cacheReadPricePerMillion": pricing["cache_read_price_per_million"],
        "cacheWritePricePerMillion": pricing["cache_write_price_per_million"],
        "unitPrice": pricing["unit_price"],
        "unitName": pricing["unit_name"],
    }
