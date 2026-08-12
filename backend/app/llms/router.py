from __future__ import annotations

import base64
from io import BytesIO
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from anthropic import AsyncAnthropic
from google import genai
from google.genai import types
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIStatusError, AsyncOpenAI

from app.services.usage_service import aggregate_token_usage


CHAT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "anthropic": "https://api.anthropic.com",
}
GEMINI_IMAGE_BASE_URL = "https://generativelanguage.googleapis.com"
IMAGE_PROVIDERS = {"openai", "gemini"}
GENERATION_TIMEOUT_SECONDS = 15 * 60


@dataclass
class SceneDraft:
    narration: str
    visualPrompt: str


@dataclass
class ParseResult:
    scenes: list[SceneDraft]
    source: str = "llm"
    warning: str = ""
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class OptimizeResult:
    optimizedScript: str
    tips: list[str]
    source: str = "llm"
    warning: str = ""
    usage: dict[str, int] = field(default_factory=dict)


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
        "gemini": "gemini-3.6-flash",
        "anthropic": "claude-3-5-sonnet-20240620",
    }.get(provider, "gpt-4o-mini")


def base_url_for(provider: str, base_url: str = "") -> str:
    base_url = base_url.strip().rstrip("/")
    if base_url:
        return base_url
    if provider in CHAT_BASE_URLS:
        return CHAT_BASE_URLS[provider]
    raise ValueError(f"unsupported provider: {provider}")


def image_base_url_for(provider: str, base_url: str = "") -> str:
    provider = provider.strip().lower()
    if provider == "openai":
        return base_url_for("openai", base_url)
    if provider == "gemini":
        base = base_url.strip().rstrip("/") if base_url else GEMINI_IMAGE_BASE_URL
        return base.removesuffix("/openai").removesuffix("/v1beta")
    raise ValueError(f"unsupported image provider: {provider}")


def _is_native_gemini_image_url(base_url: str = "") -> bool:
    return urlparse(image_base_url_for("gemini", base_url)).netloc == "generativelanguage.googleapis.com"


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
                if item.get("type") not in {"reasoning", "reasoning_content", "thinking"}:
                    parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def _reasoning_text(content: Any, additional_kwargs: dict[str, Any] | None = None) -> str:
    parts = [str((additional_kwargs or {}).get("reasoning_content") or (additional_kwargs or {}).get("reasoning") or "")]
    if isinstance(content, list):
        parts.extend(
            str(item.get("thinking") or item.get("reasoning") or item.get("text") or item.get("content") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") in {"reasoning", "reasoning_content", "thinking"}
        )
    return "".join(parts)


def _image_format_from_mime(mime_type: str) -> str:
    return {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime_type, "png")


def _gemini_image_size(value: str) -> str:
    return {"low": "1K", "medium": "2K", "high": "4K"}.get(value, value if value in {"1K", "2K", "4K"} else "2K")


def _openai_image_size(value: str) -> str:
    return {
        "1:1": "1024x1024",
        "2:3": "1024x1536",
        "3:2": "1536x1024",
        "3:4": "1024x1536",
        "4:3": "1536x1024",
        "16:9": "1536x1024",
        "9:16": "1024x1536",
        "21:9": "1536x1024",
        "9:21": "1024x1536",
    }.get(value, value)


def _openai_image_quality(value: str) -> str:
    return {"1K": "low", "2K": "medium", "4K": "high"}.get(value, value)


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
                timeout=GENERATION_TIMEOUT_SECONDS,
                max_retries=1,
                **kwargs,
            )
        return ChatOpenAI(
            model=pick_model(provider, model),
            api_key=api_key.strip(),
            base_url=base_url_for(provider, base_url),
            # Explicit base URLs disable langchain-openai's automatic stream usage.
            stream_usage=True,
            timeout=GENERATION_TIMEOUT_SECONDS,
            max_retries=1,
            **kwargs,
        )

    async def list_models(self, provider: str, api_key: str, base_url: str = "") -> list[str]:
        provider = provider.strip().lower()
        if provider == "anthropic":
            async with AsyncAnthropic(
                api_key=api_key.strip(),
                base_url=base_url_for(provider, base_url) if base_url.strip() else None,
                timeout=20,
                max_retries=1,
            ) as client:
                response = await client.models.list(limit=100)
        else:
            if provider == "gemini" and base_url.strip() and not base_url.rstrip("/").endswith("/openai"):
                base_url = base_url.rstrip("/") + "/openai"
            async with AsyncOpenAI(
                api_key=api_key.strip(),
                base_url=base_url_for(provider, base_url),
                timeout=20,
                max_retries=1,
            ) as client:
                response = await client.models.list()
        return sorted({str(item.id).strip() for item in response.data if str(item.id).strip()})

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
        with get_usage_metadata_callback() as usage_callback:
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
        usage = aggregate_token_usage(usage_callback.usage_metadata)
        if not any(usage.values()):
            usage = aggregate_token_usage(response.usage_metadata)
        return ParseResult(scenes=scenes, usage=usage)

    async def optimize_script(self, provider: str, api_key: str, model: str, script: str, base_url: str = "") -> OptimizeResult:
        script = script.strip()
        if not script:
            raise ValueError("script is empty")

        llm = self.chat_model(provider, api_key, model, base_url, temperature=0.3)
        if provider.strip().lower() != "anthropic":
            llm = llm.bind(response_format={"type": "json_object"})
        with get_usage_metadata_callback() as usage_callback:
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
        usage = aggregate_token_usage(usage_callback.usage_metadata)
        if not any(usage.values()):
            usage = aggregate_token_usage(response.usage_metadata)
        return OptimizeResult(
            optimizedScript=optimized,
            tips=tips or ["补充镜头情绪变化", "每段保持单一动作焦点", "减少重复描述，增加视觉细节"],
            usage=usage,
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
            reasoning = _reasoning_text(chunk.content, chunk.additional_kwargs)
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
        if provider.strip().lower() not in IMAGE_PROVIDERS:
            raise ValueError("image generation currently only supports provider openai/gemini")
        if not model.strip():
            raise ValueError("image purpose requires modelSeries")
        await self.generate_image(api_key, model, "Generate a simple gray square with soft light.", "1:1", "1K", base_url, provider)

    async def generate_image(
        self,
        api_key: str,
        model: str,
        prompt: str,
        size: str = "1536x1024",
        quality: str = "medium",
        base_url: str = "",
        provider: str = "openai",
    ) -> ImageResult:
        provider = provider.strip().lower()
        if provider == "gemini" and _is_native_gemini_image_url(base_url):
            return await self._generate_gemini_image(api_key, model, prompt, [], size, quality, base_url)

        client = AsyncOpenAI(
            api_key=api_key.strip(),
            base_url=image_base_url_for("openai", base_url),
            timeout=GENERATION_TIMEOUT_SECONDS,
            max_retries=0,
        )
        try:
            response = await client.images.generate(
                model=model.strip(),
                prompt=prompt.strip(),
                size=_openai_image_size(size),
                quality=_openai_image_quality(quality),
                output_format="png",
            )
        except APIStatusError as exc:
            raise ValueError(f"provider status {exc.status_code}: {exc.response.text.strip()[:220]}") from exc

        image = response.data[0] if response.data else None
        b64_json = image.b64_json if image else ""
        if not b64_json:
            raise ValueError("empty image response")
        return ImageResult(data=base64.b64decode(b64_json), format="png")

    async def edit_image(
        self,
        api_key: str,
        model: str,
        prompt: str,
        images: list[tuple[str, bytes, str]],
        size: str = "auto",
        quality: str = "medium",
        base_url: str = "",
        provider: str = "openai",
    ) -> ImageResult:
        provider = provider.strip().lower()
        if provider == "gemini" and _is_native_gemini_image_url(base_url):
            return await self._generate_gemini_image(api_key, model, prompt, images, size, quality, base_url)

        client = AsyncOpenAI(
            api_key=api_key.strip(),
            base_url=image_base_url_for("openai", base_url),
            timeout=GENERATION_TIMEOUT_SECONDS,
            max_retries=0,
        )
        files = []
        for name, data, mime_type in images:
            file = BytesIO(data)
            file.name = name
            files.append((name, file, mime_type))
        try:
            response = await client.images.edit(
                model=model.strip(),
                image=files,
                prompt=prompt.strip(),
                size=_openai_image_size(size),
                quality=_openai_image_quality(quality),
                output_format="png",
            )
        except APIStatusError as exc:
            raise ValueError(f"provider status {exc.status_code}: {exc.response.text.strip()[:220]}") from exc

        image = response.data[0] if response.data else None
        b64_json = image.b64_json if image else ""
        if not b64_json:
            raise ValueError("empty image response")
        return ImageResult(data=base64.b64decode(b64_json), format="png")

    async def _generate_gemini_image(
        self,
        api_key: str,
        model: str,
        prompt: str,
        images: list[tuple[str, bytes, str]],
        aspect_ratio: str,
        image_size: str,
        base_url: str = "",
    ) -> ImageResult:
        input_parts = [types.Part.from_text(text=prompt.strip())]
        input_parts.extend(
            types.Part.from_bytes(data=data, mime_type=mime_type)
            for _, data, mime_type in images
        )
        image_config: dict[str, str] = {"image_size": _gemini_image_size(image_size)}
        if ":" in aspect_ratio:
            image_config["aspect_ratio"] = aspect_ratio

        client = genai.Client(
            api_key=api_key.strip(),
            http_options={
                "base_url": image_base_url_for("gemini", base_url),
                "timeout": GENERATION_TIMEOUT_SECONDS * 1000,
            },
        )
        try:
            response = await client.aio.models.generate_content(
                model=model.strip(),
                contents=input_parts,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    image_config=types.ImageConfig(**image_config),
                ),
            )
        finally:
            await client.aio.aclose()

        for part in response.parts or []:
            image = part.inline_data
            if image and image.data:
                data = base64.b64decode(image.data) if isinstance(image.data, str) else image.data
                return ImageResult(data=data, format=_image_format_from_mime(str(image.mime_type or "image/png")))
        raise ValueError("empty image response")
