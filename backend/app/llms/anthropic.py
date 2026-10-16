from __future__ import annotations

import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_anthropic.chat_models import _create_usage_metadata
from langchain_core.messages.ai import UsageMetadata, add_usage, subtract_usage
from langchain_core.outputs import ChatGenerationChunk

logger = logging.getLogger(__name__)


def _usage_increment(chunk: ChatGenerationChunk, reported: UsageMetadata | None) -> UsageMetadata | None:
    usage = chunk.message.usage_metadata
    if usage is None:
        return reported
    # Anthropic reports cumulative counts; LangChain adds chunk usage. Keep the
    # initial counts when a relay omits them from the tail, without billing twice.
    increment = subtract_usage(usage, reported)
    increment["total_tokens"] = increment["input_tokens"] + increment["output_tokens"]
    chunk.message.usage_metadata = increment
    return add_usage(reported, increment)


class MeteredChatAnthropic(ChatAnthropic):
    """Retain message_start usage dropped by langchain-anthropic 1.4.8.

    Keep the SDK's content/tool parsing. Usage state belongs to each iterator,
    so concurrent calls and multiple tool rounds cannot share token counts.
    """

    def _make_message_chunk_from_anthropic_event(self, event: Any, **kwargs: Any):
        chunk, block = super()._make_message_chunk_from_anthropic_event(event, **kwargs)
        if event.type == "message_start" and chunk is not None and kwargs.get("stream_usage", True):
            chunk.usage_metadata = _create_usage_metadata(event.message.usage)
        return chunk, block

    def _warn_incomplete(self, finished: bool, usage: UsageMetadata | None) -> None:
        if not finished:
            logger.warning(
                "Anthropic stream ended without a final stop_reason; provider output usage may be missing "
                "model=%s input_tokens=%s output_tokens=%s",
                self.model,
                (usage or {}).get("input_tokens", 0),
                (usage or {}).get("output_tokens", 0),
            )

    def _stream(self, *args: Any, **kwargs: Any):
        usage = None
        finished = False
        for chunk in super()._stream(*args, **kwargs):
            usage = _usage_increment(chunk, usage)
            finished = finished or bool(chunk.message.response_metadata.get("stop_reason"))
            yield chunk
        if kwargs.get("stream_usage", self.stream_usage):
            self._warn_incomplete(finished, usage)

    async def _astream(self, *args: Any, **kwargs: Any):
        usage = None
        finished = False
        async for chunk in super()._astream(*args, **kwargs):
            usage = _usage_increment(chunk, usage)
            finished = finished or bool(chunk.message.response_metadata.get("stop_reason"))
            yield chunk
        if kwargs.get("stream_usage", self.stream_usage):
            self._warn_incomplete(finished, usage)
