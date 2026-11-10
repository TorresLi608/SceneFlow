"""Phase-one execution boundary; provider implementation is intentionally pending."""

from pydantic import SecretStr

from ..base import BaseSkill, SkillExecutionError, SkillResult
from .schema import ScriptBreakdownInput, ScriptBreakdownOutput


class ScriptBreakdownSkill(BaseSkill[ScriptBreakdownInput, ScriptBreakdownOutput]):
    name = "script_breakdown"
    description = "Break down one script into characters, scenes, props, and ordered shots."
    input_schema = ScriptBreakdownInput
    output_schema = ScriptBreakdownOutput

    async def execute(
        self, inputs: ScriptBreakdownInput, *, api_key: SecretStr | None = None,
    ) -> SkillResult[ScriptBreakdownOutput]:
        raise SkillExecutionError("NOT_IMPLEMENTED", "script_breakdown implementation is pending")

