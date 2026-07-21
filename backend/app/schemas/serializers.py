from __future__ import annotations

import json
import sqlite3
from typing import Any


def user_json(user: sqlite3.Row) -> dict[str, Any]:
    keys = user.keys()
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"] or "user",
        "isDisabled": bool(user["is_disabled"]),
        "balanceMicros": user["balance_micros"] if "balance_micros" in keys else 0,
        "level": user["level"] if "level" in keys else 1,
        "group": user["user_group"] if "user_group" in keys else "default",
        "historicalCostMicros": user["historical_cost_micros"] if "historical_cost_micros" in keys else 0,
        "requestCount": user["request_count"] if "request_count" in keys else 0,
        "createdAt": user["created_at"],
        "updatedAt": user["updated_at"],
    }


def config_json(config: sqlite3.Row) -> dict[str, Any]:
    keys = config.keys()
    return {
        "id": config["id"],
        "source": config["source"] if "source" in keys else "user",
        "name": config["name"] or "",
        "description": config["description"] or "",
        "purpose": config["purpose"],
        "provider": config["provider"],
        "baseUrl": config["base_url"] or "",
        "modelSeries": config["model_name"] or "",
        "model": config["model_name"] or "",
        "isActive": bool(config["is_active"]),
        "isEnabled": bool(config["is_enabled"]) if "is_enabled" in config.keys() else True,
        "isVerified": bool(config["is_verified"]),
        "createdAt": config["created_at"],
        "updatedAt": config["updated_at"],
        "pricingMultiplier": config["pricing_multiplier"] if "pricing_multiplier" in keys else 1,
        "inputPricePerMillion": config["input_price_per_million"] if "input_price_per_million" in keys else 0,
        "outputPricePerMillion": config["output_price_per_million"] if "output_price_per_million" in keys else 0,
        "cacheReadPricePerMillion": config["cache_read_price_per_million"] if "cache_read_price_per_million" in keys else 0,
        "cacheWritePricePerMillion": config["cache_write_price_per_million"] if "cache_write_price_per_million" in keys else 0,
        "unitPrice": config["unit_price"] if "unit_price" in keys else 0,
        "unitName": config["unit_name"] if "unit_name" in keys else "token",
    }


def official_config_json(config: sqlite3.Row, is_active: bool | None = None) -> dict[str, Any]:
    data = config_json(config)
    data["source"] = "official"
    if is_active is not None:
        data["isActive"] = is_active
    return data


def scene_json(scene: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": scene["id"],
        "order": scene["order_num"],
        "narration": scene["narration"],
        "visualPrompt": scene["visual_prompt"],
        "image": {"url": scene["image_url"] or None, "status": scene["image_status"], "progress": 0},
        "audio": {"url": scene["audio_url"] or None, "status": scene["audio_status"], "progress": 0, "duration": 0},
    }


def project_json(project: sqlite3.Row, scenes: list[sqlite3.Row]) -> dict[str, Any]:
    return {
        "id": project["id"],
        "title": project["title"] or "未命名项目",
        "originalScript": project["original_script"] or "",
        "status": project["status"] or "idle",
        "videoStatus": project["video_status"] or "idle",
        "videoProgress": project["video_progress"] or 0,
        "videoUrl": project["video_url"] or None,
        "updatedAt": project["updated_at"],
        "scenes": [scene_json(scene) for scene in scenes],
    }


def chat_session_json(session: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": session["id"],
        "title": session["title"],
        "configId": session["config_id"],
        "officialConfigId": session["official_config_id"],
        "provider": session["provider"] or "",
        "model": session["model_name"] or "",
        "createdAt": session["created_at"],
        "updatedAt": session["updated_at"],
    }


def chat_message_json(message: sqlite3.Row) -> dict[str, Any]:
    attachments = []
    if "attachments" in message.keys() and message["attachments"]:
        try:
            attachments = json.loads(message["attachments"])
        except json.JSONDecodeError:
            attachments = []
    return {
        "id": message["id"],
        "sessionId": message["session_id"],
        "role": message["role"],
        "content": message["content"],
        "attachments": attachments,
        "reasoning": message["reasoning"] or "",
        "provider": message["provider"] or "",
        "model": message["model_name"] or "",
        "createdAt": message["created_at"],
    }
