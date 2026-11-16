"""Optional LangChain boundary. The host-bound runner owns auth, billing, and storage."""

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping

from ..base import ModelSettings
from ..tool_adapter import skill_tool
from .schema import ImageGenerationInput
from .skill import ImageGenerationSkill

if TYPE_CHECKING:
    from langchain_core.tools import StructuredTool


def to_tool(
    run: Callable[[ImageGenerationInput], Awaitable[str]],
    *,
    model: ModelSettings | Mapping[str, Any],
    host_inputs: Mapping[str, Any] | None = None,
) -> "StructuredTool":
    """Bind an authorized host runner; never capture credentials in a tool schema.

    SceneFlow runners resolve configuration, check balance, invoke the skill,
    meter successful calls, store media, and serialize signed artifact links.
    `model` is the host's resolved, authorized configuration; it is bound here and never
    appears in the agent-facing schema. `host_inputs` binds further host-owned fields.
    """
    return skill_tool(ImageGenerationSkill, run, model=model, host_inputs=host_inputs)
