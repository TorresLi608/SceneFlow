"""Optional LangChain boundary. The host-bound runner owns auth, billing, and storage."""

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping

from ..tool_adapter import skill_tool
from .schema import StoryboardComposerInput
from .skill import StoryboardComposerSkill

if TYPE_CHECKING:
    from langchain_core.tools import StructuredTool


def to_tool(
    run: Callable[[StoryboardComposerInput], Awaitable[str]],
    *,
    host_inputs: Mapping[str, Any] | None = None,
) -> "StructuredTool":
    """Bind an authorized host runner; never capture credentials in a tool schema.

    SceneFlow runners resolve configuration, check balance, invoke the skill,
    meter successful calls, store media, and serialize signed artifact links.
    `host_inputs` binds host-owned fields so they never appear in the agent-facing schema.
    """
    return skill_tool(StoryboardComposerSkill, run, host_inputs=host_inputs)
