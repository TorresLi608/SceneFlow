from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


CHAT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
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
        return requested.lower() if provider in {"qwen", "deepseek", "doubao", "openai"} else requested
    return {
        "deepseek": "deepseek-chat",
        "qwen": "qwen-plus",
        "doubao": "doubao-seed-1-6-250615",
    }.get(provider, "gpt-4o-mini")


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


class ModelRouter:
    """LangChain wrapper for switching SceneFlow chat models."""

    def chat_model(self, provider: str, api_key: str, model: str, **kwargs: Any) -> ChatOpenAI:
        provider = provider.strip().lower()
        if provider not in CHAT_BASE_URLS:
            raise ValueError(f"unsupported provider: {provider}")
        return ChatOpenAI(
            model=pick_model(provider, model),
            api_key=api_key.strip(),
            base_url=CHAT_BASE_URLS[provider],
            timeout=45,
            max_retries=1,
            **kwargs,
        )

    async def validate_chat_model(self, provider: str, api_key: str, model: str) -> None:
        llm = self.chat_model(provider, api_key, model, temperature=0, max_tokens=12)
        response = await llm.ainvoke([HumanMessage(content="reply with ok")])
        if not str(response.content).strip():
            raise ValueError("empty content from provider")

    async def parse_script(self, provider: str, api_key: str, model: str, script: str) -> ParseResult:
        script = script.strip()
        if not script:
            raise ValueError("script is empty")

        llm = self.chat_model(provider, api_key, model, temperature=0.2).bind(
            response_format={"type": "json_object"}
        )
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content='You convert screenplay text into storyboard scenes. Return strict JSON only with schema: {"scenes":[{"narration":"...","visualPrompt":"..."}]}'
                ),
                HumanMessage(
                    content="Parse the script into 4-12 scenes. Keep narration concise and generate a cinematic anime visual prompt for each scene. Script:\n"
                    + script
                ),
            ]
        )

        scenes = []
        for item in _json_object(str(response.content)).get("scenes", [])[:20]:
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

    async def optimize_script(self, provider: str, api_key: str, model: str, script: str) -> OptimizeResult:
        script = script.strip()
        if not script:
            raise ValueError("script is empty")

        llm = self.chat_model(provider, api_key, model, temperature=0.3).bind(
            response_format={"type": "json_object"}
        )
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content="You are a screenplay doctor. Return strict JSON with fields optimizedScript (string) and tips (string array)."
                ),
                HumanMessage(
                    content="Polish and optimize this script for short anime video production. Keep style concise and cinematic. Script:\n"
                    + script
                ),
            ]
        )
        payload = _json_object(str(response.content))
        optimized = str(payload.get("optimizedScript", "")).strip()
        if not optimized:
            raise ValueError("optimizedScript is empty")
        tips = [str(tip).strip() for tip in payload.get("tips", []) if str(tip).strip()]
        return OptimizeResult(
            optimizedScript=optimized,
            tips=tips or ["补充镜头情绪变化", "每段保持单一动作焦点", "减少重复描述，增加视觉细节"],
        )

    async def chat(self, provider: str, api_key: str, model: str, messages: list[dict[str, str]]) -> str:
        content = ""
        async for chunk in self.chat_stream(provider, api_key, model, messages):
            if chunk["type"] == "content_delta":
                content += chunk["content"]
        content = content.strip()
        if not content:
            raise ValueError("empty content from provider")
        return content

    async def chat_stream(self, provider: str, api_key: str, model: str, messages: list[dict[str, str]]):
        provider = provider.strip().lower()
        if provider not in CHAT_BASE_URLS:
            raise ValueError(f"unsupported provider: {provider}")
        payload_messages = []
        for message in messages:
            role = (message.get("role") or "user").strip().lower()
            content = (message.get("content") or "").strip()
            if content:
                payload_messages.append({"role": role if role in {"system", "user", "assistant"} else "user", "content": content})
        if not payload_messages:
            raise ValueError("message is empty")

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{CHAT_BASE_URLS[provider]}/chat/completions",
                headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
                json={"model": pick_model(provider, model), "messages": payload_messages, "temperature": 0.4, "stream": True},
            ) as response:
                if response.status_code >= 300:
                    text = await response.aread()
                    raise ValueError(f"provider status {response.status_code}: {text.decode(errors='ignore')[:220]}")
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    payload = json.loads(data)
                    delta = (payload.get("choices") or [{}])[0].get("delta") or {}
                    reasoning = str(delta.get("reasoning_content") or delta.get("reasoning") or "")
                    content = str(delta.get("content") or "")
                    if reasoning:
                        yield {"type": "reasoning_delta", "content": reasoning}
                    if content:
                        yield {"type": "content_delta", "content": content}

    async def validate_image_model(self, provider: str, api_key: str, model: str) -> None:
        if provider.strip().lower() != "openai":
            raise ValueError("image generation currently only supports provider openai")
        if not model.strip():
            raise ValueError("image purpose requires modelSeries")
        await self.generate_image(api_key, model, "Generate a simple gray square with soft light.", "1024x1024", "low")

    async def generate_image(
        self,
        api_key: str,
        model: str,
        prompt: str,
        size: str = "1536x1024",
        quality: str = "medium",
    ) -> ImageResult:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {api_key.strip()}"},
                json={
                    "model": model.strip(),
                    "prompt": prompt.strip(),
                    "size": size,
                    "quality": quality,
                    "output_format": "png",
                },
            )
        if response.status_code >= 300:
            raise ValueError(f"provider status {response.status_code}: {response.text.strip()[:220]}")

        payload = response.json()
        b64_json = (payload.get("data") or [{}])[0].get("b64_json", "")
        if not b64_json:
            raise ValueError("empty image response")
        return ImageResult(data=base64.b64decode(b64_json), format=payload.get("output_format") or "png")
