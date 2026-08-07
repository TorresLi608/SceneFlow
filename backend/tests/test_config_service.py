from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.admin import create_default_model, update_model_config
from app.api.v1.settings import create_config, discover_models, update_config
from app.core import database
from app.core.database import db, init_db, row, rows
from app.core.security import decrypt, encrypt
from app.llms.router import _is_native_gemini_image_url, _openai_image_quality, _openai_image_size, image_base_url_for
from app.services.config_service import config_api_key, config_create_fields, config_update_fields, normalize_base_url, normalize_config_payload


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE model_configs (
            id integer PRIMARY KEY,
            user_id integer,
            source text,
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
        "INSERT INTO model_configs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 1, "user", "script", "qwen", "", "qwen-max", encrypt("old-secret-key"), 1, 1),
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


def test_discover_models_uses_submitted_connection() -> None:
    with patch("app.api.v1.settings.models.list_models", new=AsyncMock(return_value=["gpt-4.1", "o3"])) as list_models:
        result = asyncio.run(
            discover_models(
                {"provider": "openai", "baseUrl": "https://relay.example.com/v1/", "apiKey": "secret-key"},
                1,
            )
        )

    assert result == {"models": ["gpt-4.1", "o3"]}
    list_models.assert_awaited_once_with("openai", "secret-key", "https://relay.example.com/v1")


def test_base_url_rejects_private_networks() -> None:
    for value in ("http://127.0.0.1:8000/v1", "http://10.0.0.2/v1", "http://localhost/v1"):
        try:
            normalize_base_url(value)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"private base URL should fail: {value}")


def test_config_update_fields_disables_active_config() -> None:
    current = row(_conn(), "SELECT * FROM model_configs WHERE id=1")
    payload = {"isEnabled": False}
    normalized = normalize_config_payload(payload, current)

    updates = config_update_fields(payload, current, normalized)

    assert updates["is_enabled"] == 0
    assert updates["is_active"] == 0
    assert "is_verified" not in updates


def test_config_api_key_decrypts_stored_secret() -> None:
    config = row(_conn(), "SELECT encrypted_key FROM model_configs WHERE id=1")

    assert config_api_key(config) == "old-secret-key"


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


def test_video_gemini_config_is_valid() -> None:
    normalized = normalize_config_payload(
        {
            "purpose": "video",
            "provider": "gemini",
            "modelSeries": "veo-3.1-generate-preview",
            "baseUrl": "https://generativelanguage.googleapis.com/v1beta",
            "apiKey": "new-secret-key",
        }
    )

    assert normalized["purpose"] == "video"
    assert normalized["provider"] == "gemini"
    assert normalized["model"] == "veo-3.1-generate-preview"


def test_gemini_image_helpers() -> None:
    assert image_base_url_for("gemini", "https://generativelanguage.googleapis.com/v1beta/openai") == "https://generativelanguage.googleapis.com/v1beta"
    assert _is_native_gemini_image_url("https://generativelanguage.googleapis.com/v1beta/openai")
    assert not _is_native_gemini_image_url("https://relay.example.com/v1")
    assert _openai_image_size("16:9") == "1536x1024"
    assert _openai_image_quality("2K") == "medium"


def test_user_config_pricing_round_trip() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "config.db")
        try:
            init_db()
            with db() as conn:
                user_id = conn.execute(
                    "INSERT INTO users (username, password, role, is_disabled) VALUES ('pricing-user', 'x', 'user', 0)"
                ).lastrowid
            validator = AsyncMock(side_effect=AssertionError("saving must not validate the model remotely"))
            with patch("app.services.config_service.models.validate_image_model", new=validator):
                created = asyncio.run(
                    create_config(
                        {
                            "purpose": "image",
                            "provider": "openai",
                            "modelSeries": "gpt-image-1",
                            "apiKey": "new-secret-key",
                            "isActive": False,
                            "pricingMultiplier": "1.500000000000000001",
                            "inputPricePerMillion": "0.123456789012345678",
                            "unitPrice": "0.100000000000000009",
                            "unitName": "image",
                        },
                        int(user_id),
                    )
                )["config"]
                updated = asyncio.run(
                    update_config(created["id"], {"modelSeries": "gpt-image-2", "unitPrice": "0.250000000000000001"}, int(user_id))
                )["config"]
            validator.assert_not_awaited()
            assert created["pricingMultiplier"] == "1.500000000000000001"
            assert created["inputPricePerMillion"] == "0.123456789012345678"
            assert created["unitName"] == "image"
            assert updated["modelSeries"] == "gpt-image-2"
            assert updated["unitPrice"] == "0.250000000000000001"
        finally:
            database.DB_PATH = original_path


def test_price_only_admin_edit_skips_model_revalidation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "pricing-edit.db")
        try:
            init_db()
            with db() as conn:
                config_id = int(conn.execute(
                    """INSERT INTO model_configs
                    (created_at, updated_at, user_id, source, name, purpose, provider, base_url, model_name, encrypted_key,
                     is_active, is_enabled, is_verified, unit_price, unit_name)
                    VALUES ('now', 'now', NULL, 'official', 'Image', 'image', 'openai', 'https://relay.example.com/v1',
                            'gpt-image-2', ?, 1, 1, 1, 0, 'image')""",
                    (encrypt("source-secret-key"),),
                ).lastrowid)

            validator = AsyncMock(side_effect=AssertionError("saving must not validate the model remotely"))
            with patch("app.services.config_service.models.validate_image_model", new=validator):
                updated = asyncio.run(update_model_config(config_id, {
                    "source": "official",
                    "name": "Image",
                    "description": "",
                    "purpose": "image",
                    "provider": "openai",
                    "baseUrl": "https://relay.example.com/v1",
                    "modelSeries": "gpt-image-2",
                    "isActive": True,
                    "isEnabled": True,
                    "pricingMultiplier": 1,
                    "unitPrice": 0.5,
                    "unitName": "image",
                }, 1))["config"]

            validator.assert_not_awaited()
            assert updated["unitPrice"] == "0.5"
        finally:
            database.DB_PATH = original_path


def test_model_config_source_switch_preserves_id_and_key() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "config.db")
        try:
            init_db()
            with db() as conn:
                admin_id = int(conn.execute(
                    "INSERT INTO users (username, password, role, is_disabled) VALUES ('source-admin', 'x', 'superAdmin', 0)"
                ).lastrowid)
                config_id = int(conn.execute(
                    """INSERT INTO model_configs
                    (created_at, updated_at, user_id, source, name, purpose, provider, base_url, model_name, encrypted_key,
                     is_active, is_enabled, is_verified)
                    VALUES ('now', 'now', ?, 'user', 'Personal', 'script', 'openai', 'https://api.openai.com/v1', 'gpt-test', ?, 1, 1, 1)""",
                    (admin_id, encrypt("source-secret-key")),
                ).lastrowid)

            payload = {
                "name": "Converted",
                "purpose": "script",
                "provider": "openai",
                "baseUrl": "https://api.openai.com/v1",
                "modelSeries": "gpt-updated",
                "isActive": True,
                "isEnabled": True,
            }
            validator = AsyncMock(side_effect=AssertionError("saving must not validate the model remotely"))
            with patch("app.services.config_service.models.validate_chat_model", new=validator):
                created_official = asyncio.run(create_default_model({**payload, "apiKey": "official-secret-key"}, admin_id))["config"]
                official = asyncio.run(update_model_config(config_id, {**payload, "source": "official"}, admin_id))["config"]
                personal = asyncio.run(update_model_config(config_id, {**payload, "source": "user"}, admin_id))["config"]
            validator.assert_not_awaited()

            with db() as conn:
                converted = row(conn, "SELECT * FROM model_configs WHERE id=?", (config_id,))
            assert official["source"] == "official"
            assert created_official["source"] == "official"
            assert personal["source"] == "user"
            assert official["id"] == personal["id"] == config_id
            assert decrypt(converted["encrypted_key"]) == "source-secret-key"
        finally:
            database.DB_PATH = original_path


def test_legacy_model_config_tables_merge_without_losing_references() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "legacy.db")
        try:
            conn = sqlite3.connect(database.DB_PATH)
            conn.executescript(
                """
                CREATE TABLE users (
                    id integer PRIMARY KEY AUTOINCREMENT, created_at datetime, updated_at datetime, deleted_at datetime,
                    username text NOT NULL UNIQUE, password text NOT NULL, role text, is_disabled numeric
                );
                CREATE TABLE user_configs (
                    id integer PRIMARY KEY AUTOINCREMENT, created_at datetime, updated_at datetime, deleted_at datetime,
                    user_id integer NOT NULL, provider text NOT NULL, encrypted_key text NOT NULL, is_active numeric,
                    purpose text, model_name text, is_verified numeric, name text, description text
                );
                CREATE TABLE official_model_configs (
                    id integer PRIMARY KEY AUTOINCREMENT, created_at datetime, updated_at datetime, deleted_at datetime,
                    provider text NOT NULL, encrypted_key text NOT NULL, is_active numeric, purpose text,
                    model_name text, is_verified numeric, name text, description text
                );
                CREATE TABLE user_official_config_defaults (
                    user_id integer NOT NULL, purpose text NOT NULL, official_config_id integer NOT NULL,
                    created_at datetime, updated_at datetime, PRIMARY KEY(user_id, purpose)
                );
                CREATE TABLE chat_sessions (
                    id text PRIMARY KEY, created_at datetime, updated_at datetime, deleted_at datetime,
                    user_id integer NOT NULL, title text NOT NULL, config_id integer, official_config_id integer,
                    provider text, model_name text
                );
                CREATE TABLE chat_messages (
                    id text PRIMARY KEY, created_at datetime, session_id text NOT NULL, role text NOT NULL,
                    content text NOT NULL, provider text, model_name text
                );
                INSERT INTO users VALUES (1, 'now', 'now', NULL, 'legacy-user', 'x', 'user', 0);
                INSERT INTO user_configs VALUES (1, 'now', 'now', NULL, 1, 'openai', 'user-key', 1, 'script', 'user-model', 1, 'User', '');
                INSERT INTO official_model_configs VALUES (1, 'now', 'now', NULL, 'openai', 'official-key', 1, 'script', 'official-model', 1, 'Official', '');
                INSERT INTO user_official_config_defaults VALUES (1, 'script', 1, 'now', 'now');
                INSERT INTO chat_sessions VALUES ('legacy-chat', 'now', 'now', NULL, 1, 'Legacy', 1, 1, 'openai', 'user-model');
                INSERT INTO chat_messages VALUES ('legacy-message', 'now', 'legacy-chat', 'user', 'hello', 'openai', 'user-model');
                """
            )
            conn.commit()
            conn.close()

            init_db()

            with db() as conn:
                tables = {item["name"] for item in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                configs = rows(conn, "SELECT * FROM model_configs ORDER BY source")
                defaults = row(conn, "SELECT * FROM user_official_config_defaults WHERE user_id=1")
                session = row(conn, "SELECT * FROM chat_sessions WHERE id='legacy-chat'")
                message = row(conn, "SELECT * FROM chat_messages WHERE id='legacy-message'")
                foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            assert "user_configs" not in tables
            assert "official_model_configs" not in tables
            assert {config["source"] for config in configs} == {"user", "official"}
            assert session["config_id"] != session["official_config_id"]
            assert defaults["official_config_id"] == session["official_config_id"]
            assert message["content"] == "hello"
            assert foreign_key_errors == []
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_config_create_fields_rejects_disabled_default()
    test_config_update_fields_disables_active_config()
    test_image_openai_relay_config_is_valid()
    test_image_gemini_config_is_valid()
    test_video_gemini_config_is_valid()
    test_gemini_image_helpers()
    test_user_config_pricing_round_trip()
    test_price_only_admin_edit_skips_model_revalidation()
    test_model_config_source_switch_preserves_id_and_key()
    test_legacy_model_config_tables_merge_without_losing_references()
