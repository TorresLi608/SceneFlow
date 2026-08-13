from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api.v1.admin import create_default_model, delete_default_model, update_model_config
from app.api.v1.settings import activate_official_config, create_config, deactivate_official_config, discover_models, list_configs, update_config
from app.core import database
from app.core.database import db, init_db
from app.core.security import decrypt, encrypt
from app.llms.router import _is_native_gemini_image_url, _openai_image_quality, _openai_image_size, image_base_url_for
from app.models import ChatMessage, ChatSession, ModelConfig, User, UserOfficialConfigDefault
from app.services.config_service import active_model_config, config_api_key, config_create_fields, config_update_fields, normalize_base_url, normalize_config_payload, normalize_video_capabilities, video_capabilities


def _stored_config() -> ModelConfig:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    session.add(User(id=1, username="config-user", password="x"))
    config = ModelConfig(
        id=1,
        user_id=1,
        source="user",
        purpose="script",
        provider="qwen",
        base_url="",
        model_name="qwen-max",
        encrypted_key=encrypt("old-secret-key"),
        is_active=True,
        is_enabled=True,
    )
    session.add(config)
    session.flush()
    return config


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
        config_create_fields(payload, normalized)
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


def test_discover_qwen_native_models_returns_all_known_models() -> None:
    with patch("app.api.v1.settings.models.list_models", new=AsyncMock()) as list_models:
        result = asyncio.run(
            discover_models(
                {
                    "provider": "qwen",
                    "baseUrl": "https://dashscope.aliyuncs.com/api/v1",
                    "apiKey": "",
                },
                1,
            )
        )

    assert result == {
        "models": ["wan2.7-image", "wan2.7-image-pro", "wan2.7-t2v", "wan2.7-i2v", "qwen3-tts-flash:Cherry"]
    }
    list_models.assert_not_awaited()


def test_base_url_rejects_private_networks() -> None:
    for value in ("http://127.0.0.1:8000/v1", "http://10.0.0.2/v1", "http://localhost/v1"):
        try:
            normalize_base_url(value)
        except HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"private base URL should fail: {value}")


def test_config_update_fields_disables_active_config() -> None:
    current = _stored_config()
    payload = {"isEnabled": False}
    normalized = normalize_config_payload(payload, current)

    updates = config_update_fields(payload, current, normalized)

    assert updates["is_enabled"] == 0
    assert updates["is_active"] == 0


def test_config_api_key_decrypts_stored_secret() -> None:
    assert config_api_key(_stored_config()) == "old-secret-key"


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


def test_video_capabilities_are_normalized_and_stored() -> None:
    payload = {
        "purpose": "video",
        "provider": "qwen",
        "modelSeries": "wan2.7-t2v",
        "apiKey": "new-secret-key",
        "videoCapabilities": {
            "qualities": ["1080p", "480p"],
            "fps": [],
            "resolutions": [],
            "promptExtend": True,
            "minDuration": 3,
            "maxDuration": 12,
        },
    }
    normalized = normalize_config_payload(payload)
    fields = config_create_fields(payload, normalized)
    config = ModelConfig(provider="qwen", encrypted_key="x", purpose="video", video_capabilities_json=fields["video_capabilities_json"])

    assert video_capabilities(config) == {
        "qualities": ["480p", "1080p"],
        "fps": [],
        "resolutions": [],
        "promptExtend": True,
        "minDuration": 3,
        "maxDuration": 12,
        "referenceImagesRequired": False,
        "maxReferenceImages": 0,
        "referenceVideo": False,
        "drivingAudio": False,
    }
    try:
        normalize_video_capabilities({"minDuration": 15, "maxDuration": 3}, "qwen")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("invalid video duration range should fail")


def test_qwen_media_configs_are_valid() -> None:
    image = normalize_config_payload(
        {"purpose": "image", "provider": "qwen", "modelSeries": "wan2.7-image", "apiKey": "new-secret-key"}
    )
    video = normalize_config_payload(
        {"purpose": "video", "provider": "qwen", "modelSeries": "wan2.7-t2v", "apiKey": "new-secret-key"}
    )
    audio = normalize_config_payload(
        {"purpose": "audio", "provider": "qwen", "modelSeries": "qwen3-tts-flash:Cherry", "apiKey": "new-secret-key"}
    )
    assert (image["provider"], video["provider"], audio["model"]) == ("qwen", "qwen", "qwen3-tts-flash:Cherry")

    try:
        normalize_config_payload(
            {"purpose": "audio", "provider": "qwen", "modelSeries": "qwen3-tts-flash", "apiKey": "new-secret-key"}
        )
    except HTTPException as exc:
        assert exc.detail == "Qwen audio modelSeries must use model:voice"
    else:
        raise AssertionError("Qwen TTS must require a voice")


def test_gemini_image_helpers() -> None:
    assert image_base_url_for("gemini", "https://generativelanguage.googleapis.com/v1beta/openai") == "https://generativelanguage.googleapis.com"
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
            with db() as session:
                user = User(username="pricing-user", password="x", role="user", is_disabled=False)
                session.add(user)
                session.flush()
                user_id = int(user.id)
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
                    user_id,
                )
            )["config"]
            updated = asyncio.run(
                update_config(created["id"], {"modelSeries": "gpt-image-2", "unitPrice": "0.250000000000000001"}, user_id)
            )["config"]
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
            with db() as session:
                config = ModelConfig(
                    created_at="now", updated_at="now", user_id=None, source="official", name="Image", purpose="image",
                    provider="openai", base_url="https://relay.example.com/v1", model_name="gpt-image-2",
                    encrypted_key=encrypt("source-secret-key"), is_active=True, is_enabled=True,
                    unit_price=0, unit_name="image",
                )
                session.add(config)
                session.flush()
                config_id = int(config.id)

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
            assert updated["unitPrice"] == "0.5"
        finally:
            database.DB_PATH = original_path


def test_model_config_source_switch_preserves_id_and_key() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "config.db")
        try:
            init_db()
            with db() as session:
                admin = User(username="source-admin", password="x", role="superAdmin", is_disabled=False)
                session.add(admin)
                session.flush()
                admin_id = int(admin.id)
                config = ModelConfig(
                    created_at="now", updated_at="now", user_id=admin_id, source="user", name="Personal", purpose="script",
                    provider="openai", base_url="https://api.openai.com/v1", model_name="gpt-test",
                    encrypted_key=encrypt("source-secret-key"), is_active=True, is_enabled=True,
                )
                session.add(config)
                session.flush()
                config_id = int(config.id)

            payload = {
                "name": "Converted",
                "purpose": "script",
                "provider": "openai",
                "baseUrl": "https://api.openai.com/v1",
                "modelSeries": "gpt-updated",
                "isActive": True,
                "isEnabled": True,
            }
            created_official = asyncio.run(create_default_model({**payload, "apiKey": "official-secret-key"}, admin_id))["config"]
            official = asyncio.run(update_model_config(config_id, {**payload, "source": "official"}, admin_id))["config"]
            personal = asyncio.run(update_model_config(config_id, {**payload, "source": "user"}, admin_id))["config"]

            with db() as session:
                converted = session.exec(select(ModelConfig).where(ModelConfig.id == config_id)).one()
                converted_key = converted.encrypted_key
            assert official["source"] == "official"
            assert created_official["source"] == "official"
            assert personal["source"] == "user"
            assert official["id"] == personal["id"] == config_id
            assert decrypt(converted_key) == "source-secret-key"
        finally:
            database.DB_PATH = original_path


def test_legacy_model_config_tables_merge_without_losing_references() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "legacy.db")
        try:
            legacy = sqlite3.connect(database.DB_PATH)
            legacy.executescript(
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
            legacy.commit()
            legacy.close()

            init_db()

            with db() as session:
                configs = session.exec(select(ModelConfig).order_by(ModelConfig.source)).all()
                defaults = session.exec(
                    select(UserOfficialConfigDefault).where(UserOfficialConfigDefault.user_id == 1)
                ).first()
                chat = session.exec(select(ChatSession).where(ChatSession.id == "legacy-chat")).one()
                message = session.exec(select(ChatMessage).where(ChatMessage.id == "legacy-message")).one()

            check = sqlite3.connect(database.DB_PATH)
            tables = {item[0] for item in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            foreign_key_errors = check.execute("PRAGMA foreign_key_check").fetchall()
            check.close()

            assert "user_configs" not in tables
            assert "official_model_configs" not in tables
            assert {config.source for config in configs} == {"user", "official"}
            assert chat.config_id != chat.official_config_id
            assert defaults.official_config_id == chat.official_config_id
            assert message.content == "hello"
            assert foreign_key_errors == []
        finally:
            database.DB_PATH = original_path


def test_official_default_overrides_personal_config_and_is_reversible() -> None:
    with tempfile.TemporaryDirectory() as directory:
        original_path = database.DB_PATH
        database.DB_PATH = str(Path(directory) / "precedence.db")
        try:
            init_db()
            with db() as session:
                user = User(username="precedence-user", password="x", role="user", is_disabled=False)
                session.add(user)
                session.flush()
                user_id = int(user.id)

            personal = asyncio.run(create_config({
                "purpose": "script", "provider": "openai", "modelSeries": "personal-model",
                "apiKey": "personal-secret-key", "isActive": True, "name": "Personal",
            }, user_id))["config"]
            official = asyncio.run(create_default_model({
                "purpose": "script", "provider": "openai", "modelSeries": "official-model",
                "apiKey": "official-secret-key", "isActive": True, "name": "Official", "isEnabled": True,
            }, 1))["config"]

            def resolved() -> dict[str, str]:
                with db() as session:
                    return active_model_config(session, user_id, "script", "测试")

            def listed() -> tuple[dict[int, bool], dict[int, bool]]:
                payload = list_configs(user_id)
                return (
                    {item["id"]: item["isActive"] for item in payload["configs"]},
                    {item["id"]: item["isActive"] for item in payload["officialConfigs"]},
                )

            assert resolved()["model"] == "personal-model"
            mine, theirs = listed()
            assert mine[personal["id"]] is True and theirs[official["id"]] is False

            activate_official_config(official["id"], user_id)
            assert resolved()["model"] == "official-model"
            mine, theirs = listed()
            assert mine[personal["id"]] is False and theirs[official["id"]] is True
            with db() as session:
                stored = session.exec(select(ModelConfig).where(ModelConfig.id == personal["id"])).one()
                assert bool(stored.is_active) is True, "the personal choice must be preserved, not destroyed"

            deactivate_official_config(official["id"], user_id)
            assert resolved()["model"] == "personal-model"
            mine, theirs = listed()
            assert mine[personal["id"]] is True and theirs[official["id"]] is False

            # An override pointing at a config that is no longer usable must not strand the user.
            activate_official_config(official["id"], user_id)
            assert resolved()["model"] == "official-model"
            delete_default_model(official["id"], 1)
            assert resolved()["model"] == "personal-model"
            mine, _ = listed()
            assert mine[personal["id"]] is True
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_config_create_fields_rejects_disabled_default()
    test_discover_models_uses_submitted_connection()
    test_discover_qwen_native_models_returns_all_known_models()
    test_config_update_fields_disables_active_config()
    test_image_openai_relay_config_is_valid()
    test_image_gemini_config_is_valid()
    test_video_gemini_config_is_valid()
    test_video_capabilities_are_normalized_and_stored()
    test_qwen_media_configs_are_valid()
    test_gemini_image_helpers()
    test_user_config_pricing_round_trip()
    test_price_only_admin_edit_skips_model_revalidation()
    test_model_config_source_switch_preserves_id_and_key()
    test_official_default_overrides_personal_config_and_is_reversible()
    test_legacy_model_config_tables_merge_without_losing_references()
