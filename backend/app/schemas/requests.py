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


class UpdateSceneRequest(CamelModel):
    narration: str | None = Field(default=None, max_length=4000)
    visual_prompt: str | None = Field(default=None, max_length=4000)


class ReorderScenesRequest(CamelModel):
    scene_ids: list[str] = Field(min_length=1)


class ParseProjectRequest(CamelModel):
    script: str = Field(min_length=1, max_length=200_000)
    model: str | None = Field(default=None, max_length=160)
    # Reparsing replaces the storyboard the user may have edited and paid to render, so it
    # stays opt-in: without this flag a parse that would discard generated shots returns a
    # preview for confirmation instead of overwriting them.
    replace_all: bool = False


class OptimizeProjectRequest(CamelModel):
    script: str | None = Field(default=None, max_length=200_000)
    model: str | None = Field(default=None, max_length=160)


class GenerateProjectRequest(CamelModel):
    model: str | None = Field(default=None, max_length=160)


class GenerateVideoRequest(CamelModel):
    model: str | None = Field(default=None, max_length=160)
