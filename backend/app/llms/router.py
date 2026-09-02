from __future__ import annotations

import base64
from io import BytesIO
import json
import asyncio
from dataclasses import dataclass, field
import time
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
import httpx
from dashscope.aigc.image_generation import ImageGeneration

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
QWEN_MEDIA_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
IMAGE_PROVIDERS = {"openai", "gemini", "qwen"}
GENERATION_TIMEOUT_SECONDS = 15 * 60
POLL_INTERVAL_SECONDS = 5


@dataclass
class SceneDraft:
    narration: str
    visualPrompt: str


@dataclass
class ShotDraft:
    """One shot as the breakdown produces it: a frame, a performance, and a duration.

    Wider than `SceneDraft`, which only ever carried a line and a picture prompt — enough
    for a comic panel, but silent on how the camera moves, how the cut is made, and how
    long the shot runs, all of which a generated clip needs.
    """

    narration: str
    visualPrompt: str
    dialogue: str = ""
    speaker: str = ""
    shotType: str = ""
    cameraMove: str = ""
    transition: str = ""
    durationSeconds: int = 0
    videoPrompt: str = ""


@dataclass
class BreakdownResult:
    shots: list[ShotDraft]
    source: str = "llm"
    warning: str = ""
    usage: dict[str, int] = field(default_factory=dict)


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
class TextResult:
    text: str
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ImageResult:
    data: bytes
    format: str = "png"


def pick_model(provider: str, requested: str = "") -> str:
    requested = requested.strip()
    if requested:
        return requested.lower() if provider in {"deepseek", "doubao", "openai", "gemini", "anthropic"} else requested
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


def gemini_openai_base_url(base_url: str = "") -> str:
    """Use Google's OpenAI-compatible suffix only for Google's own endpoint."""
    base = base_url_for("gemini", base_url)
    parsed = urlparse(base)
    if (parsed.hostname or "").lower() != "generativelanguage.googleapis.com":
        return base
    path = parsed.path.rstrip("/")
    if path.endswith("/openai"):
        return base
    if path.endswith("/v1beta"):
        return f"{base.rstrip('/')}/openai"
    if not path:
        return "https://generativelanguage.googleapis.com/v1beta/openai"
    return base


def image_base_url_for(provider: str, base_url: str = "") -> str:
    provider = provider.strip().lower()
    if provider == "openai":
        return base_url_for("openai", base_url)
    if provider == "gemini":
        base = base_url.strip().rstrip("/") if base_url else GEMINI_IMAGE_BASE_URL
        return base.removesuffix("/openai").removesuffix("/v1beta")
    if provider == "qwen":
        base = (base_url or QWEN_MEDIA_BASE_URL).strip().rstrip("/")
        parsed = urlparse(base)
        if (parsed.hostname or "").lower() == "dashscope.aliyuncs.com":
            return f"{parsed.scheme or 'https'}://{parsed.netloc}/api/v1"
        return base
    raise ValueError(f"unsupported image provider: {provider}")


def _is_native_gemini_image_url(base_url: str = "") -> bool:
    return urlparse(image_base_url_for("gemini", base_url)).netloc == "generativelanguage.googleapis.com"


def _is_native_qwen_image_url(base_url: str = "") -> bool:
    return (urlparse(base_url or QWEN_MEDIA_BASE_URL).hostname or "").lower() == "dashscope.aliyuncs.com"


def _qwen_image_url(output: dict[str, Any]) -> str:
    results = output.get("results") or []
    if results and isinstance(results[0], dict) and results[0].get("url"):
        return str(results[0]["url"])
    for choice in output.get("choices") or []:
        content = (choice.get("message") or {}).get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "image" and item.get("image"):
                return str(item["image"])
    return ""


def _json_object(text: str) -> dict[str, Any]:
    """Extract the first complete JSON object from permissive model output.

    Models occasionally wrap JSON in Markdown or append an explanation/second JSON
    object. ``json.loads`` rejects that with ``Extra data``; ``raw_decode`` stops at
    the first complete value while still respecting braces inside JSON strings.
    """
    decoder = json.JSONDecoder()
    for candidate in _json_text_candidates(text):
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ValueError("response did not contain a JSON object")


def _json_text_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    # Some OpenAI-compatible relays serialize the whole JSON payload as text once or
    # twice. Decode that layer as JSON rather than replacing backslashes, which would
    # corrupt legitimate escaped quotes inside a dialogue field.
    for _ in range(2):
        escaped = candidates[-1].replace("\n", "\\n").replace("\r", "\\r")
        try:
            unescaped = json.loads(f'"{escaped}"')
        except json.JSONDecodeError:
            break
        if not isinstance(unescaped, str) or unescaped in candidates:
            break
        candidates.append(unescaped)
    return candidates


def _json_breakdown_payload(text: str) -> dict[str, Any]:
    """Accept either the documented object or a bare shot array."""
    decoder = json.JSONDecoder()
    candidates = _json_text_candidates(text)
    for candidate in candidates:
        for index, character in enumerate(candidate):
            if character not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and ("shots" in parsed or "scenes" in parsed):
                return parsed
            if isinstance(parsed, list):
                return {"shots": parsed}
    # Some gateways truncate a long array after one or more complete shot objects. Keep
    # the complete objects instead of failing the whole breakdown; the editor can still
    # regenerate or adjust the resulting shots.
    recovered: list[dict[str, Any]] = []
    for candidate in candidates:
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and ("narration" in parsed or "visualPrompt" in parsed) and parsed not in recovered:
                recovered.append(parsed)
    if recovered:
        return {"shots": recovered}
    raise ValueError("response did not contain a JSON object")


def _json_model(llm: Any, provider: str) -> Any:
    # JSON mode is not portable: several OpenAI-compatible deployments accept the
    # parameter but return a response shape LangChain's parser cannot handle (notably
    # ``None.tool_calls``/``None.get``).  The prompt plus the tolerant parser below is
    # enough, and keeps every provider on the same code path.
    return llm


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


def _completion_text(response: Any) -> str:
    """Read compatible chat responses without LangChain's message conversion."""
    payload = response.model_dump() if hasattr(response, "model_dump") else response
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message") or {}
        if isinstance(message, dict):
            text = _content_text(message.get("content"))
            if text:
                return text
        return str(choice.get("text") or "").strip()
    return str(payload.get("output_text") or "").strip()


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


def _image_response_field(image: Any, name: str) -> Any:
    return image.get(name) if isinstance(image, dict) else getattr(image, name, None)


async def _openai_image_result(response: Any) -> ImageResult:
    """Accept both base64 and URL responses from OpenAI-compatible image gateways."""
    items = getattr(response, "data", None) or []
    image = items[0] if items else None
    b64_json = _image_response_field(image, "b64_json") if image else ""
    if b64_json:
        return ImageResult(data=base64.b64decode(str(b64_json)), format="png")

    url = str(_image_response_field(image, "url") or "").strip() if image else ""
    if url.startswith("data:image/") and ";base64," in url:
        header, encoded = url.split(",", 1)
        mime_type = header.removeprefix("data:").split(";", 1)[0].lower()
        return ImageResult(data=base64.b64decode(encoded), format=_image_format_from_mime(mime_type))
    if not url:
        raise ValueError("empty image response (expected data[0].b64_json or data[0].url)")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("image response contained an unsupported URL")
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
        image_response = await client.get(url)
        try:
            image_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"image download status {exc.response.status_code}") from exc
    if not image_response.content:
        raise ValueError("image URL returned an empty body")
    mime_type = image_response.headers.get("content-type", "image/png").split(";", 1)[0].strip().lower()
    return ImageResult(data=image_response.content, format=_image_format_from_mime(mime_type))


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


def _qwen_image_size(aspect_ratio: str, resolution: str, has_images: bool, model: str = "") -> str:
    resolution = {"low": "1K", "medium": "2K", "high": "4K"}.get(resolution, resolution.upper())
    if resolution == "4K" and (has_images or model.strip().lower() == "wan2.7-image"):
        resolution = "2K"
    scale = 1024 if resolution == "1K" else 4096 if resolution == "4K" else 2048
    aligned = lambda value: max(16, value // 16 * 16)
    if ":" not in aspect_ratio:
        return f"{scale}*{scale}"
    return {
        "1:1": f"{scale}*{scale}",
        "2:3": f"{aligned(scale * 2 // 3)}*{scale}",
        "3:2": f"{scale}*{aligned(scale * 2 // 3)}",
        "3:4": f"{aligned(scale * 3 // 4)}*{scale}",
        "4:3": f"{scale}*{aligned(scale * 3 // 4)}",
        "16:9": f"{scale}*{aligned(scale * 9 // 16)}",
        "9:16": f"{aligned(scale * 9 // 16)}*{scale}",
        "21:9": f"{scale}*{aligned(scale * 9 // 21)}",
        "9:21": f"{aligned(scale * 9 // 21)}*{scale}",
    }.get(aspect_ratio, resolution if resolution in {"1K", "2K", "4K"} else "2K")


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
        compatible_base_url = gemini_openai_base_url(base_url) if provider == "gemini" else base_url_for(provider, base_url)
        stream_usage = kwargs.pop("stream_usage", True)
        return ChatOpenAI(
            model=pick_model(provider, model),
            api_key=api_key.strip(),
            base_url=compatible_base_url,
            # Explicit base URLs disable langchain-openai's automatic stream usage.
            stream_usage=stream_usage,
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
            async with AsyncOpenAI(
                api_key=api_key.strip(),
                base_url=gemini_openai_base_url(base_url) if provider == "gemini" else base_url_for(provider, base_url),
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
        llm = _json_model(llm, provider)
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

    async def breakdown_script(
        self,
        provider: str,
        api_key: str,
        model: str,
        system: str,
        user: str,
        base_url: str = "",
        limit: int = 40,
    ) -> BreakdownResult:
        """Split a script into shots carrying both the frame and the motion.

        Kept apart from `complete_text` because it binds a JSON response format, and apart
        from `parse_script` because the two schemas are not compatible — `parse_script`
        still serves the legacy single-screen editor, which knows nothing about camera
        moves or transitions and would break on the wider shape.
        """
        user = user.strip()
        if not user:
            raise ValueError("script is empty")

        provider_name = provider.strip().lower()
        usage: dict[str, int] = {}
        if provider_name == "anthropic":
            llm = self.chat_model(provider, api_key, model, base_url, temperature=0.3, max_tokens=8192)
            with get_usage_metadata_callback() as usage_callback:
                response = await llm.ainvoke(
                    _lc_messages([{"role": "system", "content": system}, {"role": "user", "content": user}])
                )
                usage = aggregate_token_usage(usage_callback.usage_metadata)
            text = _content_text(response.content)
            if not any(usage.values()):
                usage = aggregate_token_usage(getattr(response, "usage_metadata", None))
        else:
            # Use the same LangChain path as chat. JSON mode is deliberately not bound:
            # Gemini's OpenAI compatibility layer streams normal text correctly, while its
            # structured-response adapter may manufacture a null tool/message object.
            llm = self.chat_model(
                provider, api_key, model, base_url, temperature=0.3, max_tokens=8192, stream_usage=False
            )
            with get_usage_metadata_callback() as usage_callback:
                response = await llm.ainvoke(
                    _lc_messages([{"role": "system", "content": system}, {"role": "user", "content": user}], provider)
                )
                usage = aggregate_token_usage(usage_callback.usage_metadata)
            text = _content_text(getattr(response, "content", response))
            if not text.strip():
                extras = getattr(response, "additional_kwargs", {}) or {}
                text = str(extras.get("reasoning_content") or extras.get("reasoning") or "")
            if not any(usage.values()):
                usage = aggregate_token_usage(getattr(response, "usage_metadata", None))

        try:
            payload = _json_breakdown_payload(text)
        except ValueError as exc:
            raise ValueError("response did not contain a JSON object") from exc
        if not isinstance(payload, dict):
            raise ValueError("breakdown response must be a JSON object")
        raw = payload.get("shots")
        if not isinstance(raw, list):
            # Some models answer under the key the schema example used rather than the one
            # it asked for; accepting both is cheaper than a retry.
            raw = payload.get("scenes") if isinstance(payload.get("scenes"), list) else []

        shots: list[ShotDraft] = []
        for item in raw[:limit]:
            if not isinstance(item, dict):
                continue
            narration = str(item.get("narration", "")).strip()
            visual = str(item.get("visualPrompt", "")).strip()
            if not narration and not visual:
                continue
            try:
                duration = int(float(item.get("durationSeconds") or 0))
            except (TypeError, ValueError):
                duration = 0
            shots.append(
                ShotDraft(
                    narration=narration or _trim_prompt(visual),
                    visualPrompt=visual or f"anime storyboard frame, cinematic composition, {_trim_prompt(narration)}",
                    dialogue=str(item.get("dialogue", "")).strip(),
                    speaker=str(item.get("speaker", "")).strip(),
                    shotType=str(item.get("shotType", "")).strip()[:80],
                    cameraMove=str(item.get("cameraMove", "")).strip()[:80],
                    transition=str(item.get("transition", "")).strip()[:80],
                    # Clamped rather than rejected: an out-of-range estimate is a bad guess,
                    # not a failed breakdown, and the user can edit it afterwards.
                    durationSeconds=min(max(duration, 0), 60),
                    videoPrompt=str(item.get("videoPrompt", "")).strip(),
                )
            )
        if not shots:
            raise ValueError("no shots in breakdown output")
        return BreakdownResult(shots=shots, usage=usage)

    async def optimize_script(self, provider: str, api_key: str, model: str, script: str, base_url: str = "") -> OptimizeResult:
        script = script.strip()
        if not script:
            raise ValueError("script is empty")

        llm = self.chat_model(provider, api_key, model, base_url, temperature=0.3)
        llm = _json_model(llm, provider)
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

    async def complete_text(
        self,
        provider: str,
        api_key: str,
        model: str,
        system: str,
        user: str,
        base_url: str = "",
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> TextResult:
        """One system+user turn in, plain prose out.

        The prompt-shaped features (synopsis polish, a character state's final image
        prompt) differ only in wording, so they share this instead of each growing its own
        near-identical method. Anything needing a fixed schema stays on its own method —
        `parse_script` binds a JSON response format this deliberately does not.
        """
        user = user.strip()
        if not user:
            raise ValueError("prompt is empty")
        llm = self.chat_model(provider, api_key, model, base_url, temperature=temperature, max_tokens=max_tokens)
        with get_usage_metadata_callback() as usage_callback:
            response = await llm.ainvoke(
                _lc_messages([{"role": "system", "content": system}, {"role": "user", "content": user}])
            )
        text = _content_text(response.content).strip()
        if not text:
            raise ValueError("empty content from provider")
        usage = aggregate_token_usage(usage_callback.usage_metadata)
        if not any(usage.values()):
            usage = aggregate_token_usage(response.usage_metadata)
        return TextResult(text=text, usage=usage)

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
            raise ValueError("image generation currently only supports provider openai/gemini/qwen")
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
        if provider == "qwen" and _is_native_qwen_image_url(base_url):
            return await self._generate_qwen_image(api_key, model, prompt, [], size, quality, base_url)
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

        return await _openai_image_result(response)

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
        if provider == "qwen" and _is_native_qwen_image_url(base_url):
            return await self._generate_qwen_image(api_key, model, prompt, images, size, quality, base_url)
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

        return await _openai_image_result(response)

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

    async def _generate_qwen_image(
        self,
        api_key: str,
        model: str,
        prompt: str,
        images: list[tuple[str, bytes, str]],
        aspect_ratio: str,
        resolution: str,
        base_url: str = "",
    ) -> ImageResult:
        content = [
            {"image": f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"}
            for _, data, mime_type in images
        ]
        content.append({"text": prompt.strip()})
        payload = {
            "model": model.strip(),
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"n": 1, "size": _qwen_image_size(aspect_ratio, resolution, bool(images), model), "watermark": False},
        }
        headers = {"Authorization": f"Bearer {api_key.strip()}", "X-DashScope-Async": "enable"}
        base = image_base_url_for("qwen", base_url)
        if urlparse(base).hostname == "dashscope.aliyuncs.com":
            response = await asyncio.to_thread(
                ImageGeneration.async_call,
                model=model.strip(), api_key=api_key.strip(), messages=payload["input"]["messages"],
                n=1, size=payload["parameters"]["size"], watermark=False, base_address=base,
            )
            if getattr(response, "status_code", 200) != 200:
                raise ValueError(f"Qwen image task creation failed: {getattr(response, 'message', '') or getattr(response, 'code', '')}")
            response = await asyncio.to_thread(
                ImageGeneration.wait, response, api_key=api_key.strip(), wait_timeout=GENERATION_TIMEOUT_SECONDS
            )
            if getattr(response, "status_code", 200) != 200:
                raise ValueError(f"Qwen image task failed: {getattr(response, 'message', '') or getattr(response, 'code', '')}")
            output = getattr(response, "output", None) or {}
            status = str(output.get("task_status") or "").upper()
            if status and status != "SUCCEEDED":
                raise ValueError(f"Qwen image task {status.lower()}: {output.get('message') or output.get('code') or ''}")
            url = _qwen_image_url(output)
            if not url:
                raise ValueError("Qwen image task succeeded without an image URL")
            async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
                image_response = await client.get(url)
                image_response.raise_for_status()
                return ImageResult(image_response.content, _image_format_from_mime(image_response.headers.get("content-type", "image/png").split(";", 1)[0]))
        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.post(f"{base}/services/aigc/image-generation/generation", headers=headers, json=payload)
            response.raise_for_status()
            task_id = str(response.json().get("output", {}).get("task_id") or "")
            if not task_id:
                raise ValueError("Qwen image task creation returned no task id")
            deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                task_response = await client.get(f"{base}/tasks/{task_id}", headers={"Authorization": headers["Authorization"]})
                task_response.raise_for_status()
                output = task_response.json().get("output", {})
                status = str(output.get("task_status") or "").upper()
                if status == "SUCCEEDED":
                    url = _qwen_image_url(output)
                    if not url:
                        raise ValueError("Qwen image task succeeded without an image URL")
                    image_response = await client.get(url)
                    image_response.raise_for_status()
                    return ImageResult(image_response.content, _image_format_from_mime(image_response.headers.get("content-type", "image/png").split(";", 1)[0]))
                if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                    raise ValueError(f"Qwen image task {status.lower()}: {output.get('message') or output.get('code') or ''}")
            raise TimeoutError("Qwen image generation timed out")
