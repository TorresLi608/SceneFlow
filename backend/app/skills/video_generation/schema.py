"""Frame slots remain distinct from the ordered general-reference lists."""

from typing import Self

from pydantic import Field, model_validator

from ..base import AspectRatio, MediaArtifact, ModelSettings, NonEmptyStr, PositiveInt, SkillModel, require_media_kind


class VideoGenerationInput(SkillModel):
    model: ModelSettings
    prompt: NonEmptyStr
    camera_move: str = ""
    duration_ms: PositiveInt
    aspect_ratio: AspectRatio | None = None
    resolution: NonEmptyStr | None = None
    fps: PositiveInt | None = None
    prompt_extend: bool = False
    output_audio: bool | None = None
    first_frame: MediaArtifact | None = None
    last_frame: MediaArtifact | None = None
    reference_images: list[MediaArtifact] = Field(default_factory=list)
    reference_videos: list[MediaArtifact] = Field(default_factory=list)
    reference_audios: list[MediaArtifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_media(self) -> Self:
        for reference in (self.first_frame, self.last_frame, *self.reference_images):
            require_media_kind(reference, "image")
        for reference in self.reference_videos:
            require_media_kind(reference, "video")
        for reference in self.reference_audios:
            require_media_kind(reference, "audio")
        if self.last_frame is not None and self.first_frame is None:
            raise ValueError("last frame requires an explicit first frame")
        return self


class VideoGenerationOutput(SkillModel):
    video: MediaArtifact

    @model_validator(mode="after")
    def video_media(self) -> Self:
        require_media_kind(self.video, "video")
        return self
