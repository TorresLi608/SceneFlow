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
    # Shown on the series card. Optional: a project with no synopsis falls back to a
    # placeholder in the UI rather than blocking creation.
    description: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # A path relative to PRIVATE_GENERATED_DIR, never a URL — same rule as every other
    # asset column here, because signed links expire after ARTIFACT_TTL_DAYS.
    cover_image_path: str | None = None
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
    # The whole cast, and every prop, each tiled into one sheet. Rebuilt on demand and
    # carried into storyboard renders: providers cap how many reference images one request
    # may hold, so a series of any size has to arrive as a couple of sheets, not a crowd.
    character_sheet_path: str | None = None
    prop_sheet_path: str | None = None
    # Every voice in the show introducing itself in its own timbre, concatenated into one
    # track. Passed to the video model as a reference so it can keep speakers apart.
    voice_sheet_path: str | None = None
    # What the user wants the cover to show, in their own words. The cover used to be drawn
    # from title + synopsis, which describes the story rather than the picture — a series
    # about a betrayal got a picture of a betrayal, never the poster the user had in mind.
    cover_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # The model configuration this series uses for each kind of work. Resolution is
    # project-first: an unset column falls back to the account's active config, so existing
    # projects keep working and a user who never opens the model panel notices nothing.
    #
    # Deliberately not foreign keys, for the same reason as `characters.voice_profile_id`:
    # SQLite cannot add a constrained column in place, and a batch recreate of this table
    # reflects into the shared SQLModel metadata and reorders columns unpredictably. A
    # deleted config simply stops resolving and the fallback takes over.
    text_config_id: int | None = None
    image_config_id: int | None = None
    video_config_id: int | None = None
    audio_config_id: int | None = None
    # Generation defaults carried into every render this series starts. They live here
    # rather than being re-picked per run so a storyboard and the clips made from it agree,
    # and so the episode editor can prefill without asking the same six questions each time.
    # Validated against the selected model's declared capabilities on write.
    image_resolution: str = Field(default="2K", sa_column_kwargs={"server_default": text("'2K'")})
    image_ratio: str = Field(default="auto", sa_column_kwargs={"server_default": text("'auto'")})
    video_quality: str = Field(default="720p", sa_column_kwargs={"server_default": text("'720p'")})
    # Separate from `aspect_ratio` above: that one is the finished canvas, this is the
    # parameter handed to the video model, and the two provider vocabularies differ.
    video_aspect_ratio: str = Field(default="9:16", sa_column_kwargs={"server_default": text("'9:16'")})
    video_duration: int = Field(default=5, sa_column_kwargs={"server_default": text("5")})
    video_fps: int = Field(default=24, sa_column_kwargs={"server_default": text("24")})
    video_prompt_extend: bool = Field(default=False, sa_column_kwargs={"server_default": text("0")})


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
    # A thumbnail grid of every shot in this episode, generated in one pass before the
    # full-resolution renders. It exists to be a *style anchor*, not a deliverable: one
    # sampling fixes lighting, colour, and render style for the whole episode, and each
    # per-shot render then carries it as a reference. Without it the shots agree on faces
    # (via the cast sheet) and on nothing else.
    tone_image_path: str | None = None
    tone_image_status: str = Field(default="idle", sa_column_kwargs={"server_default": text("'idle'")})
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
    # 运镜手法 — how the camera moves through this shot. Written by the storyboard breakdown
    # and editable afterwards; it reaches the video model, not the still renderer.
    camera_move: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # 场景过渡 — how this shot enters from the one before it (hard cut, dissolve, fade).
    # A property of the seam rather than the frame, which is why it never reaches the
    # prompt that draws the still.
    transition: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # The motion prompt, kept apart from `visual_prompt`. One describes a frame, the other
    # describes what happens over several seconds; collapsing them produced clips that
    # either stood still or ignored the composition the storyboard image had already fixed.
    video_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # The shot's screen time. Written by the breakdown as an estimate and editable after;
    # 0 means "undecided", and the renderer falls back to the project default.
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
