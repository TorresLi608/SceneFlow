from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel


class Project(SQLModel, table=True):
    """A series. Its content lives in `Episode` rows, not directly on the project."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("mode IN ('comic', 'drama')"),
        Index("idx_projects_user_id", "user_id"),
        Index("idx_projects_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    user_id: int
    title: str | None = None
    original_script: str | None = None
    status: str | None = Field(default="idle", sa_column_kwargs={"server_default": text("'idle'")})
    video_url: str | None = None
    video_status: str | None = Field(default="idle", sa_column_kwargs={"server_default": text("'idle'")})
    video_progress: int | None = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    mode: str = Field(default="comic", sa_column_kwargs={"server_default": text("'comic'")})
    aspect_ratio: str = Field(default="9:16", sa_column_kwargs={"server_default": text("'9:16'")})
    width: int = Field(default=1080, sa_column_kwargs={"server_default": text("1080")})
    height: int = Field(default=1920, sa_column_kwargs={"server_default": text("1920")})
    fps: int = Field(default=24, sa_column_kwargs={"server_default": text("24")})
    target_duration_ms: int = Field(default=60000, sa_column_kwargs={"server_default": text("60000")})
    language: str = Field(default="zh-CN", sa_column_kwargs={"server_default": text("'zh-CN'")})
    style_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    negative_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    current_stage: str = Field(default="script", sa_column_kwargs={"server_default": text("'script'")})
    # World, tone, and running plot threads. Fed to the model when drafting the next episode
    # so a long-running series stays coherent instead of restarting from scratch each time.
    series_bible: str = Field(default="", sa_column_kwargs={"server_default": text("''")})


class Episode(SQLModel, table=True):
    """One installment of a series: independently written, storyboarded, and rendered."""

    __tablename__ = "episodes"
    __table_args__ = (
        CheckConstraint("episode_number > 0"),
        Index(
            "idx_episodes_project_number",
            "project_id",
            "episode_number",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("idx_episodes_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    episode_number: int
    title: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # Short recap carried into later episodes as context; cheaper than replaying full scripts.
    synopsis: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    source_text: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    status: str = Field(default="draft", sa_column_kwargs={"server_default": text("'draft'")})
    video_path: str | None = None
    video_status: str = Field(default="idle", sa_column_kwargs={"server_default": text("'idle'")})
    video_progress: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    duration_ms: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    error_message: str | None = None


class Scene(SQLModel, table=True):
    """One shot inside an episode."""

    __tablename__ = "scenes"
    __table_args__ = (
        Index("idx_scenes_project_id", "project_id"),
        Index("idx_scenes_episode_order", "episode_id", "order_num"),
        Index("idx_scenes_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    episode_id: str | None = Field(default=None, foreign_key="episodes.id", ondelete="CASCADE")
    order_num: int | None = None
    narration: str | None = None
    # Spoken by `speaker_character_id`, so it is voiced with that character's locked voice.
    # `narration` stays the narrator's line.
    dialogue: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    speaker_character_id: str | None = None
    visual_prompt: str | None = None
    shot_type: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    camera_move: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # Manual override for the shot's screen time; 0 means follow the voice track's length.
    duration_ms: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    subtitle_text: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # Asset columns hold a path relative to PRIVATE_GENERATED_DIR, never a signed URL:
    # links expire after ARTIFACT_TTL_DAYS and are minted per response by the serializer.
    image_path: str | None = None
    image_status: str | None = Field(default="idle", sa_column_kwargs={"server_default": text("'idle'")})
    audio_path: str | None = None
    audio_status: str | None = Field(default="idle", sa_column_kwargs={"server_default": text("'idle'")})
    audio_duration: float = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    # Only used in drama mode, where a shot is upgraded from a still to a generated clip.
    video_path: str | None = None
    video_status: str = Field(default="idle", sa_column_kwargs={"server_default": text("'idle'")})
    # An approved shot a batch rerun must leave alone.
    is_locked: bool = Field(default=False, sa_column_kwargs={"server_default": text("0")})
    error_message: str | None = None


class GenerationJob(SQLModel, table=True):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')"),
        Index("idx_generation_jobs_project_created", "project_id", text("created_at DESC")),
        Index("idx_generation_jobs_status_lease", "status", "lease_expires_at", "created_at"),
        Index(
            "idx_generation_jobs_idempotency",
            "user_id",
            "project_id",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: str = Field(primary_key=True)
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    episode_id: str | None = Field(default=None, foreign_key="episodes.id", ondelete="CASCADE")
    scene_id: str | None = Field(default=None, foreign_key="scenes.id", ondelete="CASCADE")
    job_type: str
    status: str = Field(default="queued", sa_column_kwargs={"server_default": text("'queued'")})
    progress: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    input_json: str = Field(default="{}", sa_column_kwargs={"server_default": text("'{}'")})
    result_json: str | None = None
    attempt: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    max_attempts: int = Field(default=3, sa_column_kwargs={"server_default": text("3")})
    idempotency_key: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    heartbeat_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
