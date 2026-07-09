from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from config_service import config_create_fields, config_update_fields, normalize_config_payload
from database import row
from model import _is_native_gemini_image_url, _openai_image_quality, _openai_image_size, image_base_url_for
from security import encrypt


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE user_configs (
            id integer PRIMARY KEY,
            purpose text,
            provider text,
            base_url text,
            model_name text,
            encrypted_key text,
            is_active numeric,
            is_enabled numeric
        )
        """
    )
    conn.execute(
        "INSERT INTO user_configs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (1, "script", "qwen", "", "qwen-max", encrypt("old-secret-key"), 1, 1),
    )
    return conn


def test_config_create_fields_rejects_disabled_default() -> None:
    payload = {
        "purpose": "script",
        "provider": "qwen",
        "modelSeries": "qwen-max",
        "apiKey": "new-secret-key",
        "isActive": True,
        "isEnabled": False,
    }
    normalized = normalize_config_payload(payload)

    try:
        config_create_fields(payload, normalized, 1)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "disabled config cannot be default"
    else:
        raise AssertionError("disabled default config should fail")


def test_config_update_fields_disables_active_config() -> None:
    current = row(_conn(), "SELECT * FROM user_configs WHERE id=1")
    payload = {"isEnabled": False}
    normalized = normalize_config_payload(payload, current)

    updates = config_update_fields(payload, current, normalized)

    assert updates["is_enabled"] == 0
    assert updates["is_active"] == 0
    assert "is_verified" not in updates


def test_image_openai_relay_config_is_valid() -> None:
    normalized = normalize_config_payload(
        {
            "purpose": "image",
            "provider": "openai",
            "modelSeries": "gpt-image-1",
            "baseUrl": "https://relay.example.com/v1",
            "apiKey": "new-secret-key",
        }
    )

    assert normalized["purpose"] == "image"
    assert normalized["provider"] == "openai"
    assert normalized["model"] == "gpt-image-1"
    assert normalized["base_url"] == "https://relay.example.com/v1"


def test_image_gemini_config_is_valid() -> None:
    normalized = normalize_config_payload(
        {
            "purpose": "image",
            "provider": "gemini",
            "modelSeries": "gemini-3.1-flash-image",
            "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
            "apiKey": "new-secret-key",
        }
    )

    assert normalized["purpose"] == "image"
    assert normalized["provider"] == "gemini"
    assert normalized["model"] == "gemini-3.1-flash-image"


def test_gemini_image_helpers() -> None:
    assert image_base_url_for("gemini", "https://generativelanguage.googleapis.com/v1beta/openai") == "https://generativelanguage.googleapis.com/v1beta"
    assert _is_native_gemini_image_url("https://generativelanguage.googleapis.com/v1beta/openai")
    assert not _is_native_gemini_image_url("https://relay.example.com/v1")
    assert _openai_image_size("16:9") == "1536x1024"
    assert _openai_image_quality("2K") == "medium"


if __name__ == "__main__":
    test_config_create_fields_rejects_disabled_default()
    test_config_update_fields_disables_active_config()
    test_image_openai_relay_config_is_valid()
    test_image_gemini_config_is_valid()
    test_gemini_image_helpers()
