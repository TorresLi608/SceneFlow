from __future__ import annotations

import asyncio
import json
import logging

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)

# Leave one final model call after the tool rounds. The graph limit is only a
# backstop; it must not cut off the normal budget-and-answer path.
MAX_TOOL_ROUNDS = 6
MAX_TOOL_CALLS = 8
MAX_CONSECUTIVE_TOOL_FAILURES = 2
CHAT_RECURSION_LIMIT = 32
FINAL_ANSWER_INSTRUCTION = (
    "Tool use has ended for this turn. Answer the user's latest question now using "
    "the tool results already available. State any missing information or failed work "
    "honestly. Do not request more tools or claim uncompleted work succeeded. "
    "Match the user's language."
)
FINAL_ANSWER_FALLBACK = "本轮已停止继续调用工具，请查看已取得的结果；未完成的部分可以缩小范围后继续提问。"


class ChatToolBudget(AgentMiddleware):
    """One instance per chat turn, created with the request-local agent.

    Cache in-flight calls too: parallel identical image/document requests must
    not generate duplicate artifacts or charge the provider more than once.
    """

    def __init__(self) -> None:
        self.model_calls = 0
        self.calls: dict[str, asyncio.Task[ToolMessage]] = {}
        self.consecutive_failures = 0
        self.repeated_call = False

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        call = request.tool_call
        key = json.dumps([call["name"], call["args"]], sort_keys=True, ensure_ascii=False)
        if key in self.calls:
            self.repeated_call = True
        else:
            if len(self.calls) >= MAX_TOOL_CALLS:
                return ToolMessage(
                    content="本轮工具调用已达上限，请根据已有结果直接回答，说明尚未完成的部分。",
                    tool_call_id=call["id"], name=call["name"],
                )

            async def execute() -> ToolMessage:
                result = await handler(request)
                if result.status == "error":
                    self.consecutive_failures += 1
                else:
                    self.consecutive_failures = 0
                return result

            self.calls[key] = asyncio.create_task(execute())
        result = await self.calls[key]
        # Graph messages must keep each requested tool_call_id, including cache hits.
        return result.model_copy(update={"tool_call_id": call["id"], "id": None})

    async def awrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        finish = (
            self.model_calls >= MAX_TOOL_ROUNDS
            or len(self.calls) >= MAX_TOOL_CALLS
            or self.consecutive_failures >= MAX_CONSECUTIVE_TOOL_FAILURES
            or self.repeated_call
        )
        self.model_calls += 1
        if not finish:
            return await handler(request)

        logger.info(
            "chat tool budget closing model_calls=%s tool_calls=%s failures=%s repeated=%s",
            self.model_calls, len(self.calls), self.consecutive_failures, self.repeated_call,
        )
        response = await handler(request.override(
            tools=[], tool_choice=None,
            system_message=SystemMessage(content=(request.system_prompt or "") + "\n" + FINAL_ANSWER_INSTRUCTION),
        ))
        # A nonconforming gateway may still return tool_calls with no tools bound.
        # End the graph safely and retain any usage metadata from that paid call.
        message = response.result[-1]
        if isinstance(message, AIMessage) and (message.tool_calls or not message.text.strip()):
            message = message.model_copy(update={
                "content": FINAL_ANSWER_FALLBACK, "tool_calls": [], "invalid_tool_calls": [],
                "additional_kwargs": {},
            })
            return ModelResponse(result=[message])
        return response
