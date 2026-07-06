from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIStatusError, AsyncOpenAI


CHAT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic": "https://api.anthropic.com",
}


@dataclass
class SceneDraft:
    narration: str
    visualPrompt: str


@dataclass
class ParseResult:
    scenes: list[SceneDraft]
    source: str = "llm"
    warning: str = ""


@dataclass
class OptimizeResult:
    optimizedScript: str
    tips: list[str]
    source: str = "llm"
    warning: str = ""


@dataclass
class ImageResult:
    data: bytes
    format: str = "png"


def pick_model(provider: str, requested: str = "") -> str:
    requested = requested.strip()
    if requested:
        return requested.lower() if provider in {"qwen", "deepseek", "doubao", "openai", "gemini", "anthropic"} else requested
    return {
        "openai": "gpt-4o-mini",
        "deepseek": "deepseek-chat",
        "qwen": "qwen-plus",
        "doubao": "doubao-seed-1-6-250615",
        "gemini": "gemini-1.5-flash",
        "anthropic": "claude-3-5-sonnet-20240620",
    }.get(provider, "gpt-4o-mini")


def base_url_for(provider: str, base_url: str = "") -> str:
    base_url = base_url.strip().rstrip("/")
    if base_url:
        return base_url
    if provider in CHAT_BASE_URLS:
        return CHAT_BASE_URLS[provider]
    raise ValueError(f"unsupported provider: {provider}")


def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("response did not contain a JSON object")
        text = text[start : end + 1]
    return json.loads(text)


def _trim_prompt(value: str) -> str:
    value = value.strip()
    return value[:100] if len(value) > 100 else value


def _anthropic_image_part(url: str) -> dict[str, Any]:
    if url.startswith("data:") and ";base64," in url:
        header, data = url.split(",", 1)
        media_type = header.removeprefix("data:").split(";", 1)[0] or "image/png"
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
    return {"type": "text", "text": f"[Image attachment: {url}]"}


def _lc_content(content: Any, provider: str) -> Any:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(content or "").strip()

    parts = []
    for item in content:
        if isinstance(item, str):
            if item.strip():
                parts.append({"type": "text", "text": item.strip()})
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = str(item.get("text") or "").strip()
            if text:
                parts.append({"type": "text", "text": text})
        elif item.get("type") in {"image", "image_url"}:
            image_url = item.get("image_url")
            url = str(
                item.get("image")
                or (image_url.get("url") if isinstance(image_url, dict) else image_url)
                or ""
            )
            if not url:
                continue
            if provider == "anthropic":
                parts.append(_anthropic_image_part(url))
            else:
                parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


def _lc_messages(messages: list[dict[str, Any]], provider: str = "") -> list[BaseMessage]:
    result: list[BaseMessage] = []
    provider = provider.strip().lower()
    for message in messages:
        role = (message.get("role") or "user").strip().lower()
        content = _lc_content(message.get("content"), provider)
        if not content:
            continue
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        else:
            result.append(HumanMessage(content=content))
    if not result:
        raise ValueError("message is empty")
    return result


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("thinking") or ""))
        return "".join(parts)
    return str(content or "")


class ModelRouter:
    def chat_model(self, provider: str, api_key: str, model: str, base_url: str = "", **kwargs: Any) -> Any:
        provider = provider.strip().lower()
        if provider == "anthropic":
            if "max_tokens" in kwargs:
                kwargs["max_tokens_to_sample"] = kwargs.pop("max_tokens")
            return ChatAnthropic(
                model_name=pick_model(provider, model),
                api_key=api_key.strip(),
                base_url=base_url_for(provider, base_url) if base_url.strip() else None,
                timeout=45,
                max_retries=1,
                **kwargs,
            )
        return ChatOpenAI(
            model=pick_model(provider, model),
            api_key=api_key.strip(),
            base_url=base_url_for(provider, base_url),
            timeout=45,
            max_retries=1,
            **kwargs,
        )

    async def validate_chat_model(self, provider: str, api_key: str, model: str, base_url: str = "") -> None:
        response = await self.chat(provider, api_key, model, [{"role": "user", "content": "reply with ok"}], base_url)
        if not response:
            raise ValueError("empty content from provider")

    async def parse_script(self, provider: str, api_key: str, model: str, script: str, base_url: str = "") -> ParseResult:
        script = script.strip()
        if not script:
            raise ValueError("script is empty")

        llm = self.chat_model(provider, api_key, model, base_url, temperature=0.2)
        if provider.strip().lower() != "anthropic":
            llm = llm.bind(response_format={"type": "json_object"})
        response = await llm.ainvoke(
            _lc_messages(
                [
                    {
                        "role": "system",
                        "content": 'You convert screenplay text into storyboard scenes. Return strict JSON only with schema: {"scenes":[{"narration":"...","visualPrompt":"..."}]}',
                    },
                    {
                        "role": "user",
                        "content": "Parse the script into 4-12 scenes. Keep narration concise and generate a cinematic anime visual prompt for each scene. Script:\n"
                        + script,
                    },
                ]
            )
        )

        scenes = []
        for item in _json_object(_content_text(response.content)).get("scenes", [])[:20]:
            narration = str(item.get("narration", "")).strip()
            visual = str(item.get("visualPrompt", "")).strip()
            if not narration:
                continue
            scenes.append(
                SceneDraft(
                    narration=narration,
                    visualPrompt=visual
                    or f"anime storyboard frame, cinematic composition, {_trim_prompt(narration)}",
                )
            )
        if not scenes:
            raise ValueError("no scenes in parsed output")
        return ParseResult(scenes=scenes)

    async def optimize_script(self, provider: str, api_key: str, model: str, script: str, base_url: str = "") -> OptimizeResult:
        script = script.strip()
        if not script:
            raise ValueError("script is empty")

        llm = self.chat_model(provider, api_key, model, base_url, temperature=0.3)
        if provider.strip().lower() != "anthropic":
            llm = llm.bind(response_format={"type": "json_object"})
        response = await llm.ainvoke(
            _lc_messages(
                [
                    {
                        "role": "system",
                        "content": "You are a screenplay doctor. Return strict JSON with fields optimizedScript (string) and tips (string array).",
                    },
                    {
                        "role": "user",
                        "content": "Polish and optimize this script for short anime video production. Keep style concise and cinematic. Script:\n"
                        + script,
                    },
                ]
            )
        )
        payload = _json_object(_content_text(response.content))
        optimized = str(payload.get("optimizedScript", "")).strip()
        if not optimized:
            raise ValueError("optimizedScript is empty")
        tips = [str(tip).strip() for tip in payload.get("tips", []) if str(tip).strip()]
        return OptimizeResult(
            optimizedScript=optimized,
            tips=tips or ["补充镜头情绪变化", "每段保持单一动作焦点", "减少重复描述，增加视觉细节"],
        )

    async def chat(self, provider: str, api_key: str, model: str, messages: list[dict[str, Any]], base_url: str = "") -> str:
        content = ""
        async for chunk in self.chat_stream(provider, api_key, model, messages, base_url):
            if chunk["type"] == "content_delta":
                content += chunk["content"]
        content = content.strip()
        if not content:
            raise ValueError("empty content from provider")
        return content

    async def chat_stream(self, provider: str, api_key: str, model: str, messages: list[dict[str, Any]], base_url: str = ""):
        llm = self.chat_model(provider, api_key, model, base_url, temperature=0.4, max_tokens=2048)
        async for chunk in llm.astream(_lc_messages(messages, provider)):
            reasoning = str(chunk.additional_kwargs.get("reasoning_content") or chunk.additional_kwargs.get("reasoning") or "")
            content = _content_text(chunk.content)
            if reasoning:
                yield {"type": "reasoning_delta", "content": reasoning}
            if content:
                yield {"type": "content_delta", "content": content}

    async def summarize_context(self, provider: str, api_key: str, model: str, context: str, base_url: str = "") -> str:
        llm = self.chat_model(provider, api_key, model, base_url, temperature=0.1, max_tokens=4096)
        response = await llm.ainvoke(
            _lc_messages(
                [
                    {
                        "role": "system",
                        "content": "Compress the conversation into a durable memory summary. Preserve user goals, decisions, constraints, unresolved tasks, and important facts. Do not answer the user.",
                    },
                    {"role": "user", "content": context},
                ]
            )
        )
        summary = _content_text(response.content).strip()
        if not summary:
            raise ValueError("empty context summary")
        return summary

    async def validate_image_model(self, provider: str, api_key: str, model: str, base_url: str = "") -> None:
        if provider.strip().lower() != "openai":
            raise ValueError("image generation currently only supports provider openai")
        if not model.strip():
            raise ValueError("image purpose requires modelSeries")
        await self.generate_image(api_key, model, "Generate a simple gray square with soft light.", "1024x1024", "low", base_url)

    async def generate_image(
        self,
        api_key: str,
        model: str,
        prompt: str,
        size: str = "1536x1024",
        quality: str = "medium",
        base_url: str = "",
    ) -> ImageResult:
        client = AsyncOpenAI(api_key=api_key.strip(), base_url=base_url_for("openai", base_url), timeout=90)
        try:
            response = await client.images.generate(
                model=model.strip(),
                prompt=prompt.strip(),
                size=size,
                quality=quality,
                output_format="png",
            )
        except APIStatusError as exc:
            raise ValueError(f"provider status {exc.status_code}: {exc.response.text.strip()[:220]}") from exc

        image = response.data[0] if response.data else None
        b64_json = image.b64_json if image else ""
        if not b64_json:
            raise ValueError("empty image response")
        return ImageResult(data=base64.b64decode(b64_json), format="png")
