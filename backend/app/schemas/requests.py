"""Shared base for every request body the API accepts.

The frontend speaks camelCase and the backend speaks snake_case. `alias_generator`
bridges both directions so neither side translates by hand, and `extra="forbid"`
turns a misspelled field into a 422 instead of a silently ignored no-op.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


ProjectMode = Literal["comic", "drama"]
AspectRatio = Literal["9:16", "16:9", "1:1"]
ProjectStage = Literal["script", "bible", "storyboard", "audio", "timeline", "export"]


class ProductionSettingsRequest(CamelModel):
    """Every field optional so a PATCH can carry just the one the user changed.

    Range checks live here for the OpenAPI schema; `project_service.production_settings`
    stays the single place that resolves defaults and cross-field consistency.
    """

    mode: ProjectMode | None = None
    aspect_ratio: AspectRatio | None = None
    width: int | None = Field(default=None, ge=256, le=4096)
    height: int | None = Field(default=None, ge=256, le=4096)
    fps: Literal[24, 30] | None = None
    target_duration_ms: int | None = Field(default=None, ge=10_000, le=600_000)
    language: str | None = Field(default=None, min_length=1, max_length=20)
    style_prompt: str | None = Field(default=None, max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    current_stage: ProjectStage | None = None


class CreateProjectRequest(CamelModel):
    title: str = Field(default="", max_length=80)
    original_script: str = Field(default="", max_length=200_000)
    production_settings: ProductionSettingsRequest = Field(default_factory=ProductionSettingsRequest)


class UpdateProjectRequest(CamelModel):
    title: str | None = Field(default=None, max_length=80)
    original_script: str | None = Field(default=None, max_length=200_000)
    series_bible: str | None = Field(default=None, max_length=200_000)


EpisodeStatus = Literal["draft", "storyboard", "generating", "done", "partial", "failed"]


class CreateEpisodeRequest(CamelModel):
    """Everything optional: the common case is "add the next episode" with nothing else."""

    title: str = Field(default="", max_length=80)
    synopsis: str = Field(default="", max_length=4000)
    source_text: str = Field(default="", max_length=200_000)


class UpdateEpisodeRequest(CamelModel):
    title: str | None = Field(default=None, max_length=80)
    synopsis: str | None = Field(default=None, max_length=4000)
    source_text: str | None = Field(default=None, max_length=200_000)
    status: EpisodeStatus | None = None


class UpdateSceneRequest(CamelModel):
    narration: str | None = Field(default=None, max_length=4000)
    dialogue: str | None = Field(default=None, max_length=4000)
    speaker_character_id: str | None = Field(default=None, max_length=64)
    visual_prompt: str | None = Field(default=None, max_length=4000)
    # Free text rather than an enum: the column carries no vocabulary and directors write
    # their own ("过肩", "handheld push-in"). Length is the only thing worth enforcing.
    shot_type: str | None = Field(default=None, max_length=80)
    camera_move: str | None = Field(default=None, max_length=80)
    # 0 hands the shot's length back to its voice track.
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    subtitle_text: str | None = Field(default=None, max_length=4000)
    is_locked: bool | None = None


class ReorderScenesRequest(CamelModel):
    scene_ids: list[str] = Field(min_length=1)
    # Order numbers restart each episode, so a reorder is always within one.
    episode_id: str | None = Field(default=None, max_length=64)


class ParseProjectRequest(CamelModel):
    script: str = Field(min_length=1, max_length=200_000)
    model: str | None = Field(default=None, max_length=160)
    # Which episode the shots land in. Omitted means the current one.
    episode_id: str | None = Field(default=None, max_length=64)
    # Reparsing replaces the storyboard the user may have edited and paid to render, so it
    # stays opt-in: without this flag a parse that would discard generated shots returns a
    # preview for confirmation instead of overwriting them.
    replace_all: bool = False


class OptimizeProjectRequest(CamelModel):
    script: str | None = Field(default=None, max_length=200_000)
    model: str | None = Field(default=None, max_length=160)


class GenerateProjectRequest(CamelModel):
    model: str | None = Field(default=None, max_length=160)
    episode_id: str | None = Field(default=None, max_length=64)


class GenerateVideoRequest(CamelModel):
    model: str | None = Field(default=None, max_length=160)
