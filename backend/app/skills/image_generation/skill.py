"""Phase-one execution boundary; provider implementation is intentionally pending."""

from pydantic import SecretStr

from ..base import BaseSkill, SkillExecutionError, SkillResult
from .schema import ImageGenerationInput, ImageGenerationOutput


class ImageGenerationSkill(BaseSkill[ImageGenerationInput, ImageGenerationOutput]):
    name = "image_generation"
    description = "Generate still images, character views, or storyboard frames from text and references."
    input_schema = ImageGenerationInput
    output_schema = ImageGenerationOutput

    async def execute(
        self, inputs: ImageGenerationInput, *, api_key: SecretStr | None = None,
    ) -> SkillResult[ImageGenerationOutput]:
        raise SkillExecutionError("NOT_IMPLEMENTED", "image_generation implementation is pending")

