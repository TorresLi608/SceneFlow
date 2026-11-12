"""Optional LangChain boundary. The host-bound runner owns auth, billing, and storage."""

from typing import TYPE_CHECKING, Any, Awaitable, Callable

from .schema import ImageGenerationInput
from .skill import ImageGenerationSkill

if TYPE_CHECKING:
    from langchain_core.tools import StructuredTool


def to_tool(run: Callable[[ImageGenerationInput], Awaitable[str]]) -> "StructuredTool":
    """Bind an authorized host runner; never capture credentials in a tool schema.

    SceneFlow runners resolve configuration, check balance, invoke the skill,
    meter successful calls, store media, and serialize signed artifact links.
    A runner must not forward untrusted provider/base URLs without host policy.
    """
    from langchain_core.tools import StructuredTool

    async def invoke(**kwargs: Any) -> str:
        return await run(ImageGenerationInput.model_validate(kwargs))

    return StructuredTool.from_function(
        coroutine=invoke, name=ImageGenerationSkill.name,
        description=ImageGenerationSkill.description,
        # A JSON schema avoids LangChain dropping camelCase aliases before invoke.
        # The Pydantic model validates inside invoke, including unknown fields.
        args_schema=ImageGenerationInput.model_json_schema(by_alias=True),
    )

