"""Shared base for every request body the API accepts.

The frontend speaks camelCase and the backend speaks snake_case. `alias_generator`
bridges both directions so neither side translates by hand, and `extra="forbid"`
turns a misspelled field into a 422 instead of a silently ignored no-op.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models import MAX_EXPORT_CLIPS


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
    description: str = Field(default="", max_length=4000)
    original_script: str = Field(default="", max_length=200_000)
    production_settings: ProductionSettingsRequest = Field(default_factory=ProductionSettingsRequest)


class UpdateProjectRequest(CamelModel):
    title: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    original_script: str | None = Field(default=None, max_length=200_000)
    series_bible: str | None = Field(default=None, max_length=200_000)


class SetProjectCoverRequest(CamelModel):
    """A cover to store on the project. `data:image/...;base64,` — the app never takes multipart."""

    # 14MB of base64 decodes to the 10MB ceiling in artifact_service.
    image_data: str = Field(min_length=1, max_length=14_000_000)


class GenerateCoverRequest(CamelModel):
    """Draw a cover from details the caller is holding, not from a stored project.

    Project-less on purpose: the create dialog needs this before a project row exists, and
    an edit dialog holds unsaved edits the stored row would not reflect. Nothing is written
    — the caller previews the result and applies it with `PUT /{id}/cover`.
    """

    title: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=4000)
    style_prompt: str = Field(default="", max_length=4000)


class OptimizeDescriptionRequest(CamelModel):
    """Polish a synopsis. Project-less and side-effect free, for the same reason as above."""

    title: str = Field(default="", max_length=80)
    description: str = Field(min_length=1, max_length=4000)
    model: str | None = Field(default=None, max_length=160)


class PromptOptimizationContext(CamelModel):
    output_language: Literal["auto", "zh", "en"] | None = None
    aspect_ratio: str | None = Field(default=None, max_length=20)
    quality: str | None = Field(default=None, max_length=20)
    duration: int | None = Field(default=None, ge=1, le=600)
    fps: int | None = Field(default=None, ge=1, le=240)
    voice: str | None = Field(default=None, max_length=160)
    speech_rate: float | None = Field(default=None, ge=0.1, le=10)
    pitch_rate: float | None = Field(default=None, ge=0.1, le=10)
    instruction: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=40)


class OptimizePromptRequest(CamelModel):
    kind: Literal["image", "video", "audio"]
    prompt: str = Field(min_length=1, max_length=10_000)
    context: PromptOptimizationContext = Field(default_factory=PromptOptimizationContext)


EpisodeStatus = Literal["draft", "storyboard", "generating", "done", "partial", "failed"]


class CreateEpisodeRequest(CamelModel):
    """The title is required: an episode list of "第 1 集 / 第 2 集" tells the user nothing."""

    title: str = Field(min_length=1, max_length=80)
    synopsis: str = Field(default="", max_length=4000)
    source_text: str = Field(default="", max_length=200_000)


class GenerateStoryboardRequest(CamelModel):
    """Render this episode's shots, anchored to a tone sheet generated first.

    `mergeReferences` trades tokens for fidelity: merged, the cast sheet, the prop sheet and
    the previous episode's tone sheet arrive as one image; separate, they arrive as several
    and cost more. `previousEpisodeId` carries continuity across an episode boundary.
    """

    previous_episode_id: str | None = Field(default=None, max_length=64)
    merge_references: bool = True
    # Without this an existing tone sheet is reused, so re-running only fills in the shots
    # that are still missing rather than resampling the episode's whole look.
    regenerate: bool = False
    scene_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)


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


class CreateSceneRequest(UpdateSceneRequest):
    episode_id: str | None = Field(default=None, max_length=64)


class ReorderScenesRequest(CamelModel):
    scene_ids: list[str] = Field(min_length=1)
    # Order numbers restart each episode, so a reorder is always within one.
    episode_id: str | None = Field(default=None, max_length=64)


class CreateCharacterRequest(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    # Comma-separated, so a script writing both "小满" and "林小满" resolves to one card.
    aliases: str = Field(default="", max_length=400)
    description: str = Field(default="", max_length=4000)
    appearance_prompt: str = Field(default="", max_length=4000)
    voice_provider: str = Field(default="", max_length=40)
    voice_model: str = Field(default="", max_length=160)
    order_num: int = Field(default=0, ge=0, le=9999)


class UpdateCharacterRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    aliases: str | None = Field(default=None, max_length=400)
    description: str | None = Field(default=None, max_length=4000)
    appearance_prompt: str | None = Field(default=None, max_length=4000)
    voice_provider: str | None = Field(default=None, max_length=40)
    voice_model: str | None = Field(default=None, max_length=160)
    # "" unbinds. A JSON null would be indistinguishable from an absent field, which the
    # PATCH handler reads as "leave it alone".
    voice_profile_id: str | None = Field(default=None, max_length=64)
    # Approving a portrait; a locked card is left alone by bulk regeneration.
    is_locked: bool | None = None
    order_num: int | None = Field(default=None, ge=0, le=9999)


class CreateCharacterStateRequest(CamelModel):
    """One look a character can appear in: an age, an outfit, a transformation.

    Every override is optional and an empty one means "unchanged", so a state that only
    swaps the voice keeps the established look. `fromEpisode` is what turns a parallel look
    into a timeline change; leaving it unset keeps the state always available.
    """

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=4000)
    appearance_prompt: str = Field(default="", max_length=4000)
    system_prompt: str = Field(default="", max_length=4000)
    final_prompt: str = Field(default="", max_length=4000)
    voice_model: str = Field(default="", max_length=160)
    order_num: int = Field(default=0, ge=0, le=9999)
    from_episode: int | None = Field(default=None, ge=1)
    # Omitted means the state stays in effect for every later episode.
    to_episode: int | None = Field(default=None, ge=1)


class UpdateCharacterStateRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    appearance_prompt: str | None = Field(default=None, max_length=4000)
    system_prompt: str | None = Field(default=None, max_length=4000)
    final_prompt: str | None = Field(default=None, max_length=4000)
    voice_model: str | None = Field(default=None, max_length=160)
    order_num: int | None = Field(default=None, ge=0, le=9999)
    from_episode: int | None = Field(default=None, ge=1)
    to_episode: int | None = Field(default=None, ge=1)


class DraftPromptRequest(CamelModel):
    """Draft an image prompt for review.

    The fields are taken from the request rather than the stored row so the dialog can draft
    against edits the user has not saved yet. `systemPrompt` overrides the built-in template.
    """

    name: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=4000)
    system_prompt: str = Field(default="", max_length=4000)
    model: str | None = Field(default=None, max_length=160)


class GenerateReferenceImageRequest(CamelModel):
    """Draw the reference from an approved prompt. Empty falls back to the stored one."""

    prompt: str = Field(default="", max_length=4000)


class UploadReferenceImageRequest(CamelModel):
    """A reference the user drew themselves. `data:image/...;base64,` — never multipart."""

    # 14MB of base64 decodes to the 10MB ceiling in artifact_service.
    image_data: str = Field(min_length=1, max_length=14_000_000)


class CreatePropRequest(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=4000)
    system_prompt: str = Field(default="", max_length=4000)
    final_prompt: str = Field(default="", max_length=4000)
    order_num: int = Field(default=0, ge=0, le=9999)


class UpdatePropRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    system_prompt: str | None = Field(default=None, max_length=4000)
    final_prompt: str | None = Field(default=None, max_length=4000)
    order_num: int | None = Field(default=None, ge=0, le=9999)


class CreateVoiceProfileRequest(CamelModel):
    """One voice in the show. Provider and model only — credentials stay on the account."""

    name: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=4000)
    voice_provider: str = Field(default="", max_length=40)
    voice_model: str = Field(default="", max_length=160)
    # The line this voice says in the merged reference track. Empty takes the built-in
    # template, which names the role rather than only demonstrating the timbre.
    sample_text: str = Field(default="", max_length=1000)
    order_num: int = Field(default=0, ge=0, le=9999)


class UpdateVoiceProfileRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=4000)
    voice_provider: str | None = Field(default=None, max_length=40)
    voice_model: str | None = Field(default=None, max_length=160)
    sample_text: str | None = Field(default=None, max_length=1000)
    order_num: int | None = Field(default=None, ge=0, le=9999)


class CreateExportRequest(CamelModel):
    """Merge chosen shots into one file, in the order given.

    Ordered by the request rather than by shot number: the video section exists to assemble
    a cut, which need not follow the storyboard.
    """

    scene_ids: list[str] = Field(min_length=1, max_length=MAX_EXPORT_CLIPS)
    # Human-facing label such as "第一集 1-6", kept so the history reads the way it was asked for.
    range_label: str = Field(default="", max_length=120)


class SetSceneCastRequest(CamelModel):
    """The full cast of a shot; sending an empty list clears it."""

    character_ids: list[str] = Field(default_factory=list, max_length=32)


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
    scene_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)


class GenerateVideoRequest(CamelModel):
    model: str | None = Field(default=None, max_length=160)
    episode_id: str | None = Field(default=None, max_length=64)
    quality: str | None = Field(default=None, max_length=16)
    aspect_ratio: str | None = Field(default=None, max_length=16)
    fps: int | None = None
    duration: int | None = None
    prompt_extend: bool = False
    # Pass the project's merged timbre reference so the model can keep speakers apart. Costs
    # more, and not every video model accepts reference audio — asking for it on one that does
    # not is a 400 rather than a silent downgrade the user would pay for and not notice.
    with_audio: bool = False
    scene_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
