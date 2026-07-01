from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from model import ModelRouter, pick_model


PORT = os.getenv("PORT", "8080")
DB_PATH = os.getenv("SCENEFLOW_DB_PATH", "./sceneflow.db")
JWT_SECRET = os.getenv("SCENEFLOW_JWT_SECRET", "dev-jwt-secret-change-me")
AES_KEY = hashlib.sha256(os.getenv("SCENEFLOW_AES_KEY", "dev-aes-key-change-me").encode()).digest()
PUBLIC_BASE_URL = os.getenv("SCENEFLOW_PUBLIC_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
GENERATED_DIR = Path(os.getenv("SCENEFLOW_GENERATED_DIR", "./generated"))

app = FastAPI(title="SceneFlow Backend")
models = ModelRouter()
clients: dict[str, set[WebSocket]] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Origin", "Content-Type", "Authorization"],
)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=GENERATED_DIR), name="generated")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db() -> Any:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                username text NOT NULL UNIQUE,
                password text NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON users(deleted_at);
            CREATE TABLE IF NOT EXISTS user_configs (
                id integer PRIMARY KEY AUTOINCREMENT,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer NOT NULL,
                provider text NOT NULL,
                encrypted_key text NOT NULL,
                is_active numeric DEFAULT false,
                purpose text DEFAULT "script",
                model_name text,
                is_verified numeric DEFAULT false,
                name text,
                description text,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_configs_user_id ON user_configs(user_id);
            CREATE INDEX IF NOT EXISTS idx_user_configs_purpose ON user_configs(purpose);
            CREATE INDEX IF NOT EXISTS idx_user_configs_deleted_at ON user_configs(deleted_at);
            CREATE TABLE IF NOT EXISTS projects (
                id text PRIMARY KEY,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                user_id integer NOT NULL,
                original_script text,
                status text DEFAULT "idle",
                video_url text,
                video_status text DEFAULT "idle"
            );
            CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
            CREATE INDEX IF NOT EXISTS idx_projects_deleted_at ON projects(deleted_at);
            CREATE TABLE IF NOT EXISTS scenes (
                id text PRIMARY KEY,
                created_at datetime,
                updated_at datetime,
                deleted_at datetime,
                project_id text NOT NULL,
                order_num integer,
                narration text,
                visual_prompt text,
                image_url text,
                image_status text DEFAULT "idle",
                audio_url text,
                audio_status text DEFAULT "idle",
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_scenes_project_id ON scenes(project_id);
            CREATE INDEX IF NOT EXISTS idx_scenes_deleted_at ON scenes(deleted_at);
            """
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


def row(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, args).fetchone()


def rows(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, args).fetchall())


def new_id(prefix: str) -> str:
    return f"{prefix.strip() or 'id'}_{secrets.token_hex(8)}"


def encrypt(value: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(AES_KEY).encrypt(nonce, value.encode(), None)).decode()


def decrypt(value: str) -> str:
    raw = base64.b64decode(value)
    return AESGCM(AES_KEY).decrypt(raw[:12], raw[12:], None).decode()


def token_for(user_id: int) -> str:
    issued = datetime.now(timezone.utc)
    return jwt.encode({"userId": user_id, "iat": issued, "exp": issued + timedelta(hours=24)}, JWT_SECRET, algorithm="HS256")


def current_user_id(authorization: str | None = Header(default=None)) -> int:
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise HTTPException(401, "missing token")
    try:
        return int(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["userId"])
    except Exception as exc:
        raise HTTPException(401, "invalid token") from exc


def user_json(user: sqlite3.Row) -> dict[str, Any]:
    return {"id": user["id"], "username": user["username"], "createdAt": user["created_at"], "updatedAt": user["updated_at"]}


def normalize_purpose(value: str) -> str:
    return (value or "script").strip().lower() or "script"


def normalize_provider(value: str) -> str:
    return (value or "").strip().lower()


def normalize_model(provider: str, value: str) -> str:
    value = (value or "").strip()
    return value.lower() if value and provider in {"qwen", "deepseek", "doubao", "openai"} else value


def validate_config_fields(purpose: str, provider: str, model: str) -> None:
    if purpose not in {"script", "image", "video"}:
        raise HTTPException(400, "invalid purpose")
    if purpose == "video":
        if provider != "seedance2.0":
            raise HTTPException(400, "video purpose only supports provider seedance2.0")
        if not model.strip():
            raise HTTPException(400, "video purpose requires modelSeries")
    elif purpose == "image":
        if provider != "openai":
            raise HTTPException(400, "image purpose currently only supports provider openai")
        if not model.strip():
            raise HTTPException(400, "image purpose requires modelSeries")
    elif provider not in {"qwen", "deepseek", "doubao", "openai"}:
        raise HTTPException(400, "provider must be one of qwen/deepseek/doubao/openai")


async def validate_provider(purpose: str, provider: str, model: str, api_key: str) -> None:
    if not api_key.strip():
        raise HTTPException(400, "apiKey is required")
    if not 8 <= len(api_key) <= 512:
        raise HTTPException(400, "apiKey length must be between 8 and 512")
    if purpose == "video":
        return
    try:
        if purpose == "image":
            await models.validate_image_model(provider, api_key, model)
        else:
            await models.validate_chat_model(provider, api_key, model)
    except Exception as exc:
        raise HTTPException(400, f"model validation failed: {str(exc).strip()[:180]}") from exc


def config_json(config: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": config["id"],
        "name": config["name"] or "",
        "description": config["description"] or "",
        "purpose": config["purpose"],
        "provider": config["provider"],
        "modelSeries": config["model_name"] or "",
        "model": config["model_name"] or "",
        "isActive": bool(config["is_active"]),
        "isVerified": bool(config["is_verified"]),
        "createdAt": config["created_at"],
        "updatedAt": config["updated_at"],
    }


def scene_json(scene: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": scene["id"],
        "order": scene["order_num"],
        "narration": scene["narration"],
        "visualPrompt": scene["visual_prompt"],
        "image": {"url": scene["image_url"] or None, "status": scene["image_status"], "progress": 0},
        "audio": {"url": scene["audio_url"] or None, "status": scene["audio_status"], "progress": 0, "duration": 0},
    }


async def broadcast(project_id: str, payload: dict[str, Any]) -> None:
    dead = []
    for ws in clients.get(project_id, set()).copy():
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.get(project_id, set()).discard(ws)


def active_model_config(conn: sqlite3.Connection, user_id: int, purpose: str, stage: str) -> dict[str, str]:
    config = row(
        conn,
        "SELECT * FROM user_configs WHERE user_id=? AND purpose=? AND is_active=1 AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1",
        (user_id, purpose),
    )
    if not config:
        raise HTTPException(400, f"{stage}未配置可用的默认模型。请前往设置，为“{purpose}”完成校验并激活默认配置后重试。")
    provider = normalize_provider(config["provider"])
    model = pick_model(provider, normalize_model(provider, config["model_name"] or ""))
    validate_config_fields(purpose, provider, model)
    if not bool(config["is_verified"]):
        raise HTTPException(400, f"{stage}当前默认模型尚未通过校验。请前往设置重新验证并激活配置后重试。")
    api_key = decrypt(config["encrypted_key"]).strip()
    if not api_key:
        raise HTTPException(400, f"{stage}当前默认模型缺少 API Key。")
    return {"provider": provider, "model": model, "apiKey": api_key}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not 3 <= len(username) <= 64 or not 6 <= len(password) <= 128:
        raise HTTPException(400, "invalid username or password length")
    stamp = now()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db() as conn:
        if row(conn, "SELECT id FROM users WHERE username=? AND deleted_at IS NULL", (username,)):
            raise HTTPException(409, "username already exists")
        cur = conn.execute(
            "INSERT INTO users (created_at, updated_at, username, password) VALUES (?, ?, ?, ?)",
            (stamp, stamp, username, hashed),
        )
        user = row(conn, "SELECT * FROM users WHERE id=?", (cur.lastrowid,))
        return {"token": token_for(user["id"]), "user": user_json(user)}


@app.post("/api/auth/login")
def login(payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE username=? AND deleted_at IS NULL", (username,))
    if not user or not bcrypt.checkpw(password.encode(), user["password"].encode()):
        raise HTTPException(401, "invalid credentials")
    return {"token": token_for(user["id"]), "user": user_json(user)}


@app.get("/api/users/me")
def get_me(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        user = row(conn, "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,))
    if not user:
        raise HTTPException(401, "user not found")
    return {"user": user_json(user)}


@app.patch("/api/users/me")
def update_me(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    updates, args = [], []
    if "username" in payload:
        username = str(payload["username"]).strip()
        if not 3 <= len(username) <= 64:
            raise HTTPException(400, "username length must be between 3 and 64")
        updates.append("username=?")
        args.append(username)
    if "password" in payload:
        password = str(payload["password"])
        if not 6 <= len(password) <= 128:
            raise HTTPException(400, "password length must be between 6 and 128")
        updates.append("password=?")
        args.append(bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
    if not updates:
        raise HTTPException(400, "no fields to update")
    with db() as conn:
        try:
            conn.execute(f"UPDATE users SET {', '.join(updates)}, updated_at=? WHERE id=? AND deleted_at IS NULL", (*args, now(), user_id))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "username already exists") from exc
        user = row(conn, "SELECT * FROM users WHERE id=?", (user_id,))
    return {"user": user_json(user)}


@app.delete("/api/users/me", status_code=204)
def delete_me(user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute("UPDATE users SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL", (now(), now(), user_id))


@app.get("/api/settings/keys")
def list_configs(user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        configs = rows(conn, "SELECT * FROM user_configs WHERE user_id=? AND deleted_at IS NULL ORDER BY updated_at DESC", (user_id,))
    return {"configs": [config_json(config) for config in configs]}


@app.get("/api/settings/keys/{config_id}")
def get_config(config_id: int, user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")
    return {"config": config_json(config)}


@app.post("/api/settings/keys/validate")
async def validate_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    purpose = normalize_purpose(str(payload.get("purpose", "")))
    provider = normalize_provider(str(payload.get("provider", "")))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or ""))
    api_key = str(payload.get("apiKey", "")).strip()
    validate_config_fields(purpose, provider, model)
    await validate_provider(purpose, provider, model, api_key)
    return {"valid": True, "purpose": purpose, "provider": provider, "modelSeries": model, "model": model}


@app.post("/api/settings/keys", status_code=201)
async def create_config(payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    purpose = normalize_purpose(str(payload.get("purpose", "")))
    provider = normalize_provider(str(payload.get("provider", "")))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or ""))
    api_key = str(payload.get("apiKey", "")).strip()
    validate_config_fields(purpose, provider, model)
    await validate_provider(purpose, provider, model, api_key)
    stamp = now()
    with db() as conn:
        if bool(payload.get("isActive")):
            conn.execute("UPDATE user_configs SET is_active=0, updated_at=? WHERE user_id=? AND purpose=? AND deleted_at IS NULL", (stamp, user_id, purpose))
        cur = conn.execute(
            """INSERT INTO user_configs
            (created_at, updated_at, user_id, name, description, purpose, provider, model_name, encrypted_key, is_active, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                stamp,
                stamp,
                user_id,
                str(payload.get("name", "")).strip()[:64],
                str(payload.get("description", "")).strip()[:255],
                purpose,
                provider,
                model,
                encrypt(api_key),
                1 if payload.get("isActive") else 0,
            ),
        )
        config = row(conn, "SELECT * FROM user_configs WHERE id=?", (cur.lastrowid,))
    return {"config": config_json(config)}


@app.patch("/api/settings/keys/{config_id}")
async def update_config(config_id: int, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        config = row(conn, "SELECT * FROM user_configs WHERE id=? AND user_id=? AND deleted_at IS NULL", (config_id, user_id))
    if not config:
        raise HTTPException(404, "config not found")

    purpose = normalize_purpose(str(payload.get("purpose", config["purpose"])))
    provider = normalize_provider(str(payload.get("provider", config["provider"])))
    model = normalize_model(provider, str(payload.get("modelSeries") or payload.get("model") or config["model_name"] or ""))
    validate_config_fields(purpose, provider, model)
    api_key = str(payload["apiKey"]).strip() if "apiKey" in payload else decrypt(config["encrypted_key"])
    if any(key in payload for key in ("apiKey", "provider", "modelSeries", "model", "purpose")) or payload.get("isActive"):
        await validate_provider(purpose, provider, model, api_key)

    updates: dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = str(payload["name"]).strip()[:64]
    if "description" in payload:
        updates["description"] = str(payload["description"]).strip()[:255]
    if "purpose" in payload:
        updates["purpose"] = purpose
    if "provider" in payload:
        updates["provider"] = provider
    if any(key in payload for key in ("modelSeries", "model")):
        updates["model_name"] = model
    if "apiKey" in payload:
        if not 8 <= len(str(payload["apiKey"])) <= 512:
            raise HTTPException(400, "apiKey length must be between 8 and 512")
        updates["encrypted_key"] = encrypt(api_key)
    if any(key in payload for key in ("apiKey", "provider", "modelSeries", "model", "purpose")) or payload.get("isActive"):
        updates["is_verified"] = 1
    if "isActive" in payload:
        updates["is_active"] = 1 if payload["isActive"] else 0
    if not updates:
        raise HTTPException(400, "no fields to update")

    stamp = now()
    with db() as conn:
        if payload.get("isActive"):
            conn.execute("UPDATE user_configs SET is_active=0, updated_at=? WHERE user_id=? AND purpose=? AND id<>? AND deleted_at IS NULL", (stamp, user_id, purpose, config_id))
        conn.execute(
            f"UPDATE user_configs SET {', '.join(f'{key}=?' for key in updates)}, updated_at=? WHERE id=? AND user_id=?",
            (*updates.values(), stamp, config_id, user_id),
        )
        config = row(conn, "SELECT * FROM user_configs WHERE id=?", (config_id,))
    return {"config": config_json(config)}


@app.delete("/api/settings/keys/{config_id}", status_code=204)
def delete_config(config_id: int, user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        conn.execute("UPDATE user_configs SET deleted_at=?, updated_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL", (now(), now(), config_id, user_id))


async def parse_project_model(conn: sqlite3.Connection, user_id: int, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    script = str(payload.get("script", "")).strip()
    if not script:
        raise HTTPException(400, "script is required")
    existing = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
    stamp = now()
    if existing and existing["user_id"] != user_id:
        raise HTTPException(403, "project does not belong to current user")
    if existing:
        conn.execute("UPDATE projects SET original_script=?, status='parsing', updated_at=? WHERE id=?", (script, stamp, project_id))
    else:
        conn.execute(
            "INSERT INTO projects (id, created_at, updated_at, user_id, original_script, status, video_status) VALUES (?, ?, ?, ?, ?, 'parsing', 'idle')",
            (project_id, stamp, stamp, user_id, script),
        )
    config = active_model_config(conn, user_id, "script", "故事生成/分镜拆分")
    return {"script": script, "config": config}


@app.post("/api/projects/{project_id}/parse")
async def parse_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    if not project_id.strip():
        raise HTTPException(400, "invalid project id")
    with db() as conn:
        data = await parse_project_model(conn, user_id, project_id, payload)

    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "parsing"}})
    config = data["config"]
    try:
        result = await models.parse_script(config["provider"], config["apiKey"], str(payload.get("model") or config["model"]), data["script"])
    except Exception as exc:
        with db() as conn:
            conn.execute("UPDATE projects SET status='idle', updated_at=? WHERE id=?", (now(), project_id))
        raise HTTPException(502, "failed to parse script: " + str(exc)) from exc

    stamp = now()
    with db() as conn:
        conn.execute("UPDATE projects SET original_script=?, status='idle', updated_at=? WHERE id=?", (data["script"], stamp, project_id))
        conn.execute("UPDATE scenes SET deleted_at=?, updated_at=? WHERE project_id=? AND deleted_at IS NULL", (stamp, stamp, project_id))
        scene_rows = []
        for index, draft in enumerate(result.scenes, start=1):
            scene_id = new_id("scene")
            conn.execute(
                """INSERT INTO scenes
                (id, created_at, updated_at, project_id, order_num, narration, visual_prompt, image_status, audio_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'idle', 'idle')""",
                (scene_id, stamp, stamp, project_id, index, draft.narration, draft.visualPrompt),
            )
            scene_rows.append(row(conn, "SELECT * FROM scenes WHERE id=?", (scene_id,)))

    for scene in scene_rows:
        await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"order": scene["order_num"], "narration": scene["narration"], "visualPrompt": scene["visual_prompt"], "parseStatus": "ready"}})
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "sceneCount": len(scene_rows), "source": result.source, "warning": result.warning}})
    return {"projectId": project_id, "status": "idle", "source": result.source, "warning": result.warning, "scenes": [scene_json(scene) for scene in scene_rows]}


def project_and_scenes(conn: sqlite3.Connection, project_id: str, user_id: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    project = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
    if not project:
        raise HTTPException(404, "project not found")
    if project["user_id"] != user_id:
        raise HTTPException(403, "project does not belong to current user")
    return project, rows(conn, "SELECT * FROM scenes WHERE project_id=? AND deleted_at IS NULL ORDER BY order_num ASC", (project_id,))


@app.post("/api/projects/{project_id}/optimize")
async def optimize_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        project, _ = project_and_scenes(conn, project_id, user_id)
        script = str(payload.get("script") or project["original_script"] or "").strip()
        if not script:
            raise HTTPException(400, "script is required")
        config = active_model_config(conn, user_id, "script", "故事生成/剧本优化")
    try:
        result = await models.optimize_script(config["provider"], config["apiKey"], str(payload.get("model") or config["model"]), script)
    except Exception as exc:
        raise HTTPException(502, "failed to optimize script: " + str(exc)) from exc
    with db() as conn:
        conn.execute("UPDATE projects SET original_script=?, status='idle', updated_at=? WHERE id=?", (result.optimizedScript, now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "idle", "optimizedScript": result.optimizedScript, "warning": result.warning}})
    return {"projectId": project_id, "optimizedScript": result.optimizedScript, "tips": result.tips, "source": result.source, "warning": result.warning, "appliedToProject": True}


@app.post("/api/projects/{project_id}/generate", status_code=202)
async def generate_project(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        project, scenes = project_and_scenes(conn, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        if project["status"] == "generating":
            raise HTTPException(409, "project is already generating")
        try:
            config, warning = active_model_config(conn, user_id, "image", "镜头提示词生成"), ""
        except HTTPException as image_error:
            config = active_model_config(conn, user_id, "script", "镜头提示词生成回退")
            warning = "图片生成默认模型当前不可用，已回退到剧本/提示词默认模型。原始原因：" + str(image_error.detail)
        conn.execute("UPDATE projects SET status='generating', updated_at=? WHERE id=?", (now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "generating"}})
    asyncio.create_task(run_generation(project_id, [dict(scene) for scene in scenes], config))
    return {"projectId": project_id, "status": "generating", "model": str(payload.get("model") or config["model"]), "provider": config["provider"], "imageModel": config["model"], "warning": warning, "sceneCount": len(scenes)}


async def run_generation(project_id: str, scenes: list[dict[str, Any]], config: dict[str, str]) -> None:
    semaphore = asyncio.Semaphore(3)

    async def one(scene: dict[str, Any]) -> None:
        async with semaphore:
            await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "generating", "imageProgress": 5, "audioStatus": "generating", "audioProgress": 0, "errorMsg": ""}})
            with db() as conn:
                conn.execute("UPDATE scenes SET image_status='generating', updated_at=? WHERE id=?", (now(), scene["id"]))
            try:
                prompt = build_image_prompt(scene)
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "generating", "imageProgress": 20, "errorMsg": ""}})
                if config["provider"] != "openai":
                    raise ValueError("image generation currently only supports provider openai")
                image = await models.generate_image(config["apiKey"], config["model"], prompt)
                image_url = persist_scene_image(project_id, scene["id"], image.data, image.format)
                with db() as conn:
                    conn.execute("UPDATE scenes SET image_status='success', image_url=?, updated_at=? WHERE id=?", (image_url, now(), scene["id"]))
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "success", "imageProgress": 100, "imageUrl": image_url, "errorMsg": ""}})
            except Exception as exc:
                with db() as conn:
                    conn.execute("UPDATE scenes SET image_status='error', updated_at=? WHERE id=?", (now(), scene["id"]))
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"imageStatus": "error", "imageProgress": 0, "errorMsg": "AI 图片生成失败：" + str(exc)[:220]}})

            for index, progress in enumerate([25, 50, 75, 100]):
                await asyncio.sleep((110 + ((int(scene["order_num"]) + index) % 5) * 40) / 1000)
                await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"audioStatus": "generating", "audioProgress": progress, "errorMsg": ""}})
            audio_url = f"https://example.com/audio/{scene['id']}.mp3"
            with db() as conn:
                conn.execute("UPDATE scenes SET audio_status='success', audio_url=?, updated_at=? WHERE id=?", (audio_url, now(), scene["id"]))
            await broadcast(project_id, {"type": "SCENE_UPDATE", "projectId": project_id, "sceneId": scene["id"], "data": {"audioStatus": "success", "audioProgress": 100, "audioUrl": audio_url, "audioDuration": 2.0 + (int(scene["order_num"]) % 5 + 1) * 0.8, "errorMsg": ""}})

    await asyncio.gather(*(one(scene) for scene in scenes))
    with db() as conn:
        conn.execute("UPDATE projects SET status='done', updated_at=? WHERE id=?", (now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "done"}})


def build_image_prompt(scene: dict[str, Any]) -> str:
    narration = str(scene.get("narration") or "").strip()
    visual = str(scene.get("visual_prompt") or narration).strip()
    return f"Create a cinematic anime storyboard frame for a short video. Keep one clear subject, strong composition, dramatic lighting, high detail, no text, no watermark. Scene narration: {narration}. Visual direction: {visual}."


def persist_scene_image(project_id: str, scene_id: str, data: bytes, ext: str) -> str:
    scene_dir = GENERATED_DIR / "projects" / project_id
    scene_dir.mkdir(parents=True, exist_ok=True)
    ext = (ext or "png").strip().lower()
    path = scene_dir / f"{scene_id}.{ext}"
    path.write_bytes(data)
    return f"{PUBLIC_BASE_URL}/generated/projects/{project_id}/{path.name}"


@app.post("/api/projects/{project_id}/generate-video", status_code=202)
async def generate_video(project_id: str, payload: dict[str, Any], user_id: int = Depends(current_user_id)) -> dict[str, Any]:
    with db() as conn:
        project, scenes = project_and_scenes(conn, project_id, user_id)
        if not scenes:
            raise HTTPException(400, "no scenes available, parse script first")
        if project["status"] == "video_generating":
            raise HTTPException(409, "project video is already generating")
        config = active_model_config(conn, user_id, "video", "视频生成")
        model = str(payload.get("model") or config["model"]).strip()
        conn.execute("UPDATE projects SET status='video_generating', video_status='generating', updated_at=? WHERE id=?", (now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "video_generating", "videoStatus": "generating", "videoModel": model}})
    asyncio.create_task(run_video_generation(project_id, model))
    return {"projectId": project_id, "status": "video_generating", "model": model}


async def run_video_generation(project_id: str, model: str) -> None:
    for progress in [10, 25, 40, 60, 75, 90, 100]:
        await asyncio.sleep(0.35)
        await broadcast(project_id, {"type": "VIDEO_UPDATE", "projectId": project_id, "data": {"videoStatus": "generating", "videoProgress": progress, "videoModel": model}})
    video_url = f"https://example.com/video/{project_id}.mp4"
    with db() as conn:
        conn.execute("UPDATE projects SET status='done', video_status='success', video_url=?, updated_at=? WHERE id=?", (video_url, now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_UPDATE", "projectId": project_id, "data": {"status": "done", "videoStatus": "success", "videoUrl": video_url, "videoModel": model}})


@app.delete("/api/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, user_id: int = Depends(current_user_id)) -> None:
    with db() as conn:
        project = row(conn, "SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
        if not project:
            return
        if project["user_id"] != user_id:
            raise HTTPException(403, "project does not belong to current user")
        conn.execute("UPDATE projects SET deleted_at=?, updated_at=? WHERE id=?", (now(), now(), project_id))
    await broadcast(project_id, {"type": "PROJECT_DELETED", "projectId": project_id})


@app.websocket("/ws/projects/{project_id}")
async def project_ws(websocket: WebSocket, project_id: str, token: str = "") -> None:
    token = token.strip()
    if not token:
        token = (websocket.headers.get("authorization") or "").replace("Bearer", "").strip()
    try:
        user_id = int(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["userId"])
    except Exception:
        await websocket.close(code=1008)
        return
    with db() as conn:
        project = row(conn, "SELECT user_id FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,))
        if project and project["user_id"] != user_id:
            await websocket.close(code=1008)
            return
    await websocket.accept()
    clients.setdefault(project_id, set()).add(websocket)
    await broadcast(project_id, {"type": "WS_CONNECTED", "projectId": project_id, "data": {"connectedAt": now()}})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        clients.get(project_id, set()).discard(websocket)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Any, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
