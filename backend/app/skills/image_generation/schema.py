"""Still images, reference edits, view sheets, and compatible GIF parameters."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ..base import AspectRatio, MediaArtifact, ModelSettings, NonEmptyStr, PositiveInt, SkillModel, require_media_kind


class ImageGenerationInput(SkillModel):
    model: ModelSettings
    prompt: NonEmptyStr
    purpose: Literal["image", "character_views", "storyboard_frame"] = "image"
    references: list[MediaArtifact] = Field(default_factory=list)
    views: list[NonEmptyStr] = Field(default_factory=list)
    aspect_ratio: AspectRatio = "auto"
    resolution: NonEmptyStr = "2K"
    width: PositiveInt | None = None
    height: PositiveInt | None = None
    output_format: Literal["png", "gif"] = "png"
    frame_count: Annotated[int, Field(strict=True, ge=2, le=16)] | None = None
    frame_duration_ms: Annotated[int, Field(strict=True, ge=20, le=2000, multiple_of=10)] | None = None

    @model_validator(mode="after")
    def valid_options(self) -> Self:
        for reference in self.references:
            require_media_kind(reference, "image")
        if (self.width is None) != (self.height is None):
            raise ValueError("width and height must be supplied together")
        if self.purpose == "character_views" and not self.views:
            raise ValueError("character views require an explicit ordered views list")
        if self.views and self.purpose != "character_views":
            raise ValueError("views require character_views purpose")
        if self.output_format != "gif" and (self.frame_count is not None or self.frame_duration_ms is not None):
            raise ValueError("animation options require GIF output")
        return self


class GeneratedImage(SkillModel):
    media: MediaArtifact
    view: NonEmptyStr | None = None

    @model_validator(mode="after")
    def image_media(self) -> Self:
        require_media_kind(self.media, "image")
        return self


class ImageGenerationOutput(SkillModel):
    images: list[GeneratedImage] = Field(min_length=1)
    source: Literal["text-to-image", "image-to-image"]
