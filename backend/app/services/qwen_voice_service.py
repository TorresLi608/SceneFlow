from __future__ import annotations

import base64
import re
from typing import Any

import httpx

DESIGN_MODEL = "qwen-voice-design"
# Voice design is slow enough that a short client timeout would abandon work already paid
# for, so this matches the provider's own worst case rather than a polite default.
DESIGN_TIMEOUT_SECONDS = 15 * 60


def _base_url(config: dict[str, Any]) -> str:
    return (str(config.get("baseUrl") or "https://dashscope.aliyuncs.com/api/v1")).rstrip("/")


async def _call(config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """One design request.

    Async rather than blocking: this is what a user's 停止 button cancels. A synchronous
    `httpx.post` here held a threadpool worker for up to fifteen minutes and ignored the
    disconnect entirely, so stopping did nothing but hide the spinner.
    """
    async with httpx.AsyncClient(timeout=DESIGN_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{_base_url(config)}/services/audio/tts/customization",
            headers={"Authorization": f"Bearer {config['apiKey']}", "Content-Type": "application/json"},
            json={"model": DESIGN_MODEL, "input": payload, "parameters": {"sample_rate": 24000, "response_format": "wav"}},
        )
        response.raise_for_status()
        data = response.json()
    if not isinstance(data.get("output"), dict):
        raise ValueError("Qwen voice design returned no output")
    return data["output"]


async def create_voice(
    config: dict[str, Any],
    voice_prompt: str,
    preview_text: str,
    preferred_name: str,
) -> tuple[str, bytes]:
    preferred_name = re.sub(r"[^A-Za-z0-9_]", "_", preferred_name).strip("_")[:64] or "sceneflow_voice"
    target_model = str(config.get("model") or "").strip()
    if not target_model:
        raise ValueError("Qwen voice design target model is required")
    output = await _call(
        config,
        {
            "action": "create",
            "target_model": target_model,
            "preferred_name": preferred_name,
            "voice_prompt": voice_prompt,
            "preview_text": preview_text,
            "language": "zh",
        },
    )
    voice_id = str(output.get("voice") or "").strip()
    if not voice_id:
        raise ValueError("Qwen voice design returned no voice id")
    audio = output.get("preview_audio") if isinstance(output.get("preview_audio"), dict) else {}
    if not audio:
        audio = output.get("audio") if isinstance(output.get("audio"), dict) else {}
    if not audio and output.get("audio_url"):
        audio = {"url": output["audio_url"]}
    if audio.get("data"):
        return voice_id, base64.b64decode(str(audio["data"]))
    if audio.get("url"):
        async with httpx.AsyncClient(timeout=DESIGN_TIMEOUT_SECONDS) as client:
            response = await client.get(str(audio["url"]))
            response.raise_for_status()
            return voice_id, response.content
    raise ValueError("Qwen voice design returned no preview audio")
