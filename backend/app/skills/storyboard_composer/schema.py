"""A portable edit decision list; composing metadata does not render an MP4."""

from typing import Literal, Self

from pydantic import Field, model_validator

from ..base import MediaArtifact, Milliseconds, NonEmptyStr, PositiveInt, SkillModel, require_media_kind


class SubtitleCue(SkillModel):
    text: NonEmptyStr
    start_ms: Milliseconds
    end_ms: PositiveInt

    @model_validator(mode="after")
    def ordered_time(self) -> Self:
        if self.end_ms <= self.start_ms:
            raise ValueError("subtitle end must follow start")
        return self


class AudioCue(SkillModel):
    media: MediaArtifact
    start_ms: Milliseconds = 0
    duration_ms: PositiveInt

    @model_validator(mode="after")
    def audio_media(self) -> Self:
        require_media_kind(self.media, "audio")
        return self


class ComposerShot(SkillModel):
    key: NonEmptyStr
    visual: MediaArtifact
    duration_ms: PositiveInt
    source_start_ms: Milliseconds = 0
    transition: str = "cut"
    audio: list[AudioCue] = Field(default_factory=list)
    subtitles: list[SubtitleCue] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_segment(self) -> Self:
        if not self.visual.media_type.startswith(("image/", "video/")):
            raise ValueError("shot visual must be image or video media")
        if self.visual.media_type.startswith("image/") and self.source_start_ms:
            raise ValueError("still images have no source time offset")
        if self.visual.duration_ms is not None and self.source_start_ms + self.duration_ms > self.visual.duration_ms:
            raise ValueError("shot exceeds source media duration")
        if any(cue.start_ms + cue.duration_ms > self.duration_ms for cue in self.audio):
            raise ValueError("audio cue exceeds shot duration")
        if any(cue.end_ms > self.duration_ms for cue in self.subtitles):
            raise ValueError("subtitle exceeds shot duration")
        return self


class StoryboardComposerInput(SkillModel):
    title: NonEmptyStr
    width: PositiveInt = 1080
    height: PositiveInt = 1920
    fps: PositiveInt = 24
    shots: list[ComposerShot] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_keys(self) -> Self:
        if len({shot.key for shot in self.shots}) != len(self.shots):
            raise ValueError("shot keys must be unique")
        return self


class TimelineShot(ComposerShot):
    start_ms: Milliseconds


class StoryboardComposerOutput(SkillModel):
    format_version: Literal["1.0"] = "1.0"
    title: NonEmptyStr
    width: PositiveInt
    height: PositiveInt
    fps: PositiveInt
    duration_ms: PositiveInt
    timeline: list[TimelineShot] = Field(min_length=1)

    @model_validator(mode="after")
    def contiguous_timeline(self) -> Self:
        cursor = 0
        keys: set[str] = set()
        for shot in self.timeline:
            if shot.start_ms != cursor or shot.key in keys:
                raise ValueError("timeline must be contiguous with unique shot keys")
            keys.add(shot.key)
            cursor += shot.duration_ms
        if cursor != self.duration_ms:
            raise ValueError("timeline duration does not match shots")
        return self
