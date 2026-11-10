"""Optional LangChain boundary. The host-bound runner owns auth, billing, and storage."""

from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .schema import VoiceDesignInput
from .skill import VoiceDesignSkill

if TYPE_CHECKING:
    from langchain_core.tools import StructuredTool


def to_tool(run: Callable[[VoiceDesignInput], Awaitable[str]]) -> "StructuredTool":
    """Bind an authorized host runner; never capture credentials in a tool schema.

    SceneFlow runners resolve configuration, check balance, invoke the skill,
    meter successful calls, store media, and serialize signed artifact links.
    A runner must not forward untrusted provider/base URLs without host policy.
    """
    from langchain_core.tools import StructuredTool

    async def invoke(**kwargs: Any) -> str:
        return await run(VoiceDesignInput.model_validate(kwargs))

    return StructuredTool.from_function(
        coroutine=invoke, name=VoiceDesignSkill.name,
        description=VoiceDesignSkill.description,
        # A JSON schema avoids LangChain dropping camelCase aliases before invoke.
        # The Pydantic model validates inside invoke, including unknown fields.
        args_schema=VoiceDesignInput.model_json_schema(by_alias=True),
    )

