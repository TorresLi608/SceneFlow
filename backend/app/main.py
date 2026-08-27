from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import (
    admin,
    auth,
    characters,
    chat,
    episodes,
    exports,
    images,
    jobs,
    prompts,
    projects,
    props,
    settings,
    usage,
    users,
    videos,
    voices,
    user_voices,
    websocket,
)
from app.core.config import CORS_ORIGINS, PRIVATE_GENERATED_DIR
from app.core.database import init_db
from app.core.logging import configure_logging
from app.services import job_handlers  # noqa: F401 -- registers the generation job handlers
from app.services.job_worker import worker
from app.services.project_service import release_orphaned_runs


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()
    # A render is an in-process task, so a restart kills it holding the project's busy lock
    # and nothing else can ever release it. Startup is the one point where "no run is in
    # flight" is a fact rather than a guess.
    release_orphaned_runs()
    # Paid generation runs here rather than inside the request, so that stopping is a
    # database operation instead of a hung-up socket. See `app/services/job_worker.py`.
    worker.start()
    try:
        yield
    finally:
        await worker.stop()


app = FastAPI(title="SceneFlow Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Origin", "Content-Type", "Authorization"],
)

PRIVATE_GENERATED_DIR.mkdir(parents=True, exist_ok=True)
PRIVATE_GENERATED_DIR.chmod(0o700)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(settings.router)
app.include_router(chat.router)
app.include_router(images.router)
app.include_router(videos.router)
app.include_router(usage.router)
app.include_router(prompts.router)
app.include_router(projects.router)
app.include_router(episodes.router)
app.include_router(characters.router)
app.include_router(props.router)
app.include_router(voices.router)
app.include_router(user_voices.router)
app.include_router(exports.router)
app.include_router(jobs.router)
app.include_router(websocket.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Any, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


def validation_message(exc: RequestValidationError) -> str:
    """Flatten pydantic's error list into one readable sentence.

    `loc` starts with the source ("body", "query"), which tells the user nothing; what they
    need is the field name and what was wrong with it.
    """
    parts = []
    for error in exc.errors():
        field = ".".join(str(item) for item in error.get("loc", ()) if item not in {"body", "query", "path"})
        message = str(error.get("msg") or "invalid value")
        parts.append(f"{field}: {message}" if field else message)
    return "; ".join(parts) or "request validation failed"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Any, exc: RequestValidationError) -> JSONResponse:
    # Without this, rejected bodies would come back as {"detail": [...]} while every other
    # error is {"error": "..."}, leaving the client with two shapes to parse.
    return JSONResponse(status_code=422, content={"error": validation_message(exc)})
