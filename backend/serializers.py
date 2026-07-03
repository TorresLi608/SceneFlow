from __future__ import annotations

import sqlite3
from typing import Any


def user_json(user: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"] or "user",
        "isDisabled": bool(user["is_disabled"]),
        "createdAt": user["created_at"],
        "updatedAt": user["updated_at"],
    }


def config_json(config: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": config["id"],
        "source": "user",
        "name": config["name"] or "",
        "description": config["description"] or "",
        "purpose": config["purpose"],
        "provider": config["provider"],
        "baseUrl": config["base_url"] or "",
        "modelSeries": config["model_name"] or "",
        "model": config["model_name"] or "",
        "isActive": bool(config["is_active"]),
        "isVerified": bool(config["is_verified"]),
        "createdAt": config["created_at"],
        "updatedAt": config["updated_at"],
    }


def official_config_json(config: sqlite3.Row) -> dict[str, Any]:
    data = config_json(config)
    data["source"] = "official"
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
    return {
        "id": message["id"],
        "sessionId": message["session_id"],
        "role": message["role"],
        "content": message["content"],
        "reasoning": message["reasoning"] or "",
        "provider": message["provider"] or "",
        "model": message["model_name"] or "",
        "createdAt": message["created_at"],
    }
