"""Phase-one execution boundary; provider implementation is intentionally pending."""

from pydantic import SecretStr

from ..base import BaseSkill, SkillExecutionError, SkillResult
from .schema import VoiceDesignInput, VoiceDesignOutput


class VoiceDesignSkill(BaseSkill[VoiceDesignInput, VoiceDesignOutput]):
    name = "voice_design"
    description = "Design, clone, or select voices and synthesize dialogue audio."
    input_schema = VoiceDesignInput
    output_schema = VoiceDesignOutput

    async def execute(
        self, inputs: VoiceDesignInput, *, api_key: SecretStr | None = None,
    ) -> SkillResult[VoiceDesignOutput]:
        raise SkillExecutionError("NOT_IMPLEMENTED", "voice_design implementation is pending")

