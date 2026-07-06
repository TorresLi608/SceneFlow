from __future__ import annotations

import sqlite3

from fastapi import HTTPException

from config_service import config_create_fields, config_update_fields, normalize_config_payload
from database import row
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


if __name__ == "__main__":
    test_config_create_fields_rejects_disabled_default()
    test_config_update_fields_disables_active_config()
