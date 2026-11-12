"""Phase-one execution boundary; provider implementation is intentionally pending."""

from pydantic import SecretStr

from ..base import BaseSkill, SkillExecutionError, SkillResult
from .schema import StoryboardComposerInput, StoryboardComposerOutput


class StoryboardComposerSkill(BaseSkill[StoryboardComposerInput, StoryboardComposerOutput]):
    name = "storyboard_composer"
    description = "Sequence shot visuals, audio cues, and subtitles into a portable timeline."
    input_schema = StoryboardComposerInput
    output_schema = StoryboardComposerOutput

    async def execute(
        self, inputs: StoryboardComposerInput, *, api_key: SecretStr | None = None,
    ) -> SkillResult[StoryboardComposerOutput]:
        raise SkillExecutionError("NOT_IMPLEMENTED", "storyboard_composer implementation is pending")

