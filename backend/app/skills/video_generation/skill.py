"""Phase-one execution boundary; provider implementation is intentionally pending."""

from pydantic import SecretStr

from ..base import BaseSkill, SkillExecutionError, SkillResult
from .schema import VideoGenerationInput, VideoGenerationOutput


class VideoGenerationSkill(BaseSkill[VideoGenerationInput, VideoGenerationOutput]):
    name = "video_generation"
    description = "Generate a video from text, frame slots, and ordered media references."
    input_schema = VideoGenerationInput
    output_schema = VideoGenerationOutput

    async def execute(
        self, inputs: VideoGenerationInput, *, api_key: SecretStr | None = None,
    ) -> SkillResult[VideoGenerationOutput]:
        raise SkillExecutionError("NOT_IMPLEMENTED", "video_generation implementation is pending")

