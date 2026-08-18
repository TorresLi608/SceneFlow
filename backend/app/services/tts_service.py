from __future__ import annotations

import asyncio
import base64
import json
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import httpx
import edge_tts
import dashscope
from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer


DASHSCOPE_TTS_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
_DASHSCOPE_TTS_LOCK = threading.Lock()


async def synthesize(text: str, config: dict[str, str], output: Path, options: dict[str, Any] | None = None) -> tuple[Path, float]:
    text = text.strip()
    if not text:
        raise ValueError("TTS text is required")
    provider = config["provider"]
    output.parent.mkdir(parents=True, exist_ok=True)
    if provider == "edge":
        try:
            await edge_tts.Communicate(text, config["model"] or "zh-CN-XiaoxiaoNeural").save(str(output))
        except Exception:
            output = output.with_suffix(".wav")
            await asyncio.to_thread(_system_tts, text, "Tingting", output)
    elif provider == "system":
        await asyncio.to_thread(_system_tts, text, config["model"], output)
    elif provider == "openai":
        await _openai_tts(text, config, output)
    elif provider == "qwen":
        await _qwen_tts(text, config, output, options)
    else:
        raise ValueError("audio purpose only supports provider edge/system/openai/qwen")
    return output, _duration(output, len(text) / 4.5)


def _duration(path: Path, fallback: float) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        try:
            return max(1.0, float(json.loads(result.stdout)["format"]["duration"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return max(1.0, fallback)


def _system_tts(text: str, voice: str, output: Path) -> None:
    if say := shutil.which("say"):
        subprocess.run(
            [say, "-v", voice or "Tingting", "--data-format=LEI16@22050", "-o", str(output), text],
            check=True,
            capture_output=True,
        )
        return
    if espeak := shutil.which("espeak-ng") or shutil.which("espeak"):
        command = [espeak, "-w", str(output), "-v", "zh" if not voice or voice == "Tingting" else voice]
        subprocess.run([*command, text], check=True, capture_output=True)
        return
    raise RuntimeError("local TTS requires macOS say or espeak-ng")


async def _openai_tts(text: str, config: dict[str, str], output: Path) -> None:
    base_url = (config.get("baseUrl") or "https://api.openai.com/v1").rstrip("/")
    async with httpx.AsyncClient(timeout=15 * 60) as client:
        response = await client.post(
            f"{base_url}/audio/speech",
            headers={"Authorization": f"Bearer {config['apiKey']}"},
            json={"model": config["model"], "voice": "alloy", "input": text, "response_format": "wav"},
        )
        response.raise_for_status()
        output.write_bytes(response.content)


async def _qwen_tts(text: str, config: dict[str, str], output: Path, options: dict[str, Any] | None = None) -> None:
    model, separator, voice = config["model"].partition(":")
    if not model or (not separator and model != "qwen-audio-3.0-tts-flash") or (separator and not voice):
        raise ValueError("Qwen audio modelSeries must use model:voice, for example qwen3-tts-flash:Cherry")
    base_url = (config.get("baseUrl") or "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
    if (httpx.URL(base_url).host or "").lower() == "dashscope.aliyuncs.com":
        await asyncio.to_thread(_qwen_tts_sdk, text, config["apiKey"], model, voice, output, options)
        return
    input_data: dict[str, Any] = {"text": text, "voice": voice}
    parameters = {key: value for key, value in (options or {}).items() if value is not None}
    if parameters.get("format"):
        format_name = str(parameters["format"])
        parameters["format"] = format_name.split("_", 1)[0].lower()
        parameters["sample_rate"] = int(format_name.split("_", 2)[1].removesuffix("HZ")) if "_" in format_name else 22050
    async with httpx.AsyncClient(timeout=15 * 60, follow_redirects=True) as client:
        response = await client.post(
            f"{base_url}/services/aigc/multimodal-generation/generation",
            headers={"Authorization": f"Bearer {config['apiKey']}"},
            json={"model": model, "input": input_data, **({"parameters": parameters} if parameters else {})},
        )
        response.raise_for_status()
        audio = response.json().get("output", {}).get("audio", {})
        if audio.get("url"):
            audio_response = await client.get(audio["url"])
            audio_response.raise_for_status()
            output.write_bytes(audio_response.content)
            return
        if audio.get("data"):
            output.write_bytes(base64.b64decode(audio["data"]))
            return
        raise ValueError("Qwen TTS returned no audio")


def _qwen_tts_sdk(text: str, api_key: str, model: str, voice: str, output: Path, options: dict[str, Any] | None = None) -> None:
    # The official SDK reads its API key and WebSocket URL from module globals.
    # Keep the mutation short and serialized so concurrent users cannot cross credentials.
    with _DASHSCOPE_TTS_LOCK:
        previous_key = dashscope.api_key
        previous_url = dashscope.base_websocket_api_url
        dashscope.api_key = api_key.strip()
        dashscope.base_websocket_api_url = DASHSCOPE_TTS_WS_URL
        try:
            kwargs: dict[str, Any] = {"model": model, "voice": voice}
            if options:
                format_name = str(options.get("format") or "").strip()
                if format_name:
                    kwargs["format"] = getattr(AudioFormat, format_name)
                for key in ("volume", "speech_rate", "pitch_rate", "seed", "instruction", "language_hints"):
                    if options.get(key) is not None:
                        kwargs[key] = options[key]
            audio = SpeechSynthesizer(**kwargs).call(text, timeout_millis=15 * 60 * 1000)
        finally:
            dashscope.api_key = previous_key
            dashscope.base_websocket_api_url = previous_url
    if not audio:
        raise ValueError("Qwen TTS returned no audio")
    output.write_bytes(audio)
