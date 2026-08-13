from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import re
import time
from typing import Any

import httpx
from google import genai
from google.genai import types


DOUBAO_VIDEO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
GEMINI_VIDEO_BASE_URL = "https://generativelanguage.googleapis.com"
QWEN_VIDEO_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpeg|jpg|webp));base64,(.+)$", re.DOTALL)
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
POLL_INTERVAL_SECONDS = 5
GENERATION_TIMEOUT_SECONDS = 15 * 60


@dataclass(frozen=True)
class VideoSettings:
    resolution: str
    ratio: str


@dataclass(frozen=True)
class VideoResult:
    data: bytes
    format: str = "mp4"


VIDEO_SETTINGS = {
    "1280x720": VideoSettings("720p", "16:9"),
    "720x1280": VideoSettings("720p", "9:16"),
    "1024x1024": VideoSettings("720p", "1:1"),
    "1920x1080": VideoSettings("1080p", "16:9"),
}


def parse_reference(value: dict[str, Any]) -> tuple[bytes, str]:
    match = DATA_URL_RE.match(str(value.get("data") or ""))
    if not match:
        raise ValueError("reference image must be a png/jpeg/webp data URL")
    mime_type, encoded = match.groups()
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("invalid reference image data") from exc
    if not data or len(data) > MAX_REFERENCE_BYTES:
        raise ValueError("reference image must be 1 byte to 10MB")
    return data, "image/jpeg" if mime_type in {"image/jpeg", "image/jpg"} else mime_type


def resolve_video_settings(provider: str, resolution: str, fps: int, duration: int) -> VideoSettings:
    provider = provider.strip().lower()
    if provider not in {"doubao", "gemini", "qwen"}:
        raise ValueError("video generation currently only supports provider doubao/gemini/qwen")
    if fps != 24:
        raise ValueError("Doubao, Gemini, and Qwen video models currently only support 24 FPS")
    if not 4 <= duration <= 15:
        raise ValueError("duration must be between 4 and 15 seconds")
    settings = VIDEO_SETTINGS.get(resolution)
    if not settings:
        raise ValueError("unsupported video resolution")
    if provider == "gemini" and settings.ratio == "1:1":
        raise ValueError("Gemini video models do not support 1:1 output")
    return settings


def validate_qwen_video_input(model: str, reference: dict[str, Any] | None) -> None:
    is_i2v = "-i2v" in model.strip().lower()
    if is_i2v and not reference:
        raise ValueError(f"Qwen image-to-video model {model} requires a reference image")
    if reference and not is_i2v:
        raise ValueError(f"Qwen text-to-video model {model} does not accept a reference image; use wan2.7-i2v")


def build_doubao_payload(
    model: str,
    prompt: str,
    settings: VideoSettings,
    duration: int,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if reference:
        data, mime_type = parse_reference(reference)
        encoded = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                "role": "first_frame",
            }
        )
    return {
        "model": model,
        "content": content,
        "resolution": settings.resolution,
        "ratio": settings.ratio,
        "duration": duration,
        "watermark": False,
    }


def _provider_error(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)
        return str(error or payload.get("message") or payload)
    return str(payload)


def _response_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"


def gemini_video_base_url(base_url: str = "") -> str:
    return (base_url or GEMINI_VIDEO_BASE_URL).strip().rstrip("/").removesuffix("/openai").removesuffix("/v1beta")


async def _generate_doubao_video(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings,
    duration: int,
    reference: dict[str, Any] | None,
    base_url: str,
) -> VideoResult:
    payload = build_doubao_payload(model, prompt, settings, duration, reference)
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(GENERATION_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.post(
            f"{(base_url or DOUBAO_VIDEO_BASE_URL).rstrip('/')}/contents/generations/tasks",
            headers=headers,
            json=payload,
        )
        if response.is_error:
            raise ValueError(f"Doubao task creation failed: {_provider_error(_response_payload(response))[:220]}")
        create_result = _response_payload(response)
        task_id = str(create_result.get("id") if isinstance(create_result, dict) else "").strip()
        if not task_id:
            raise ValueError("Doubao task creation returned no task id")

        deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            task_response = await client.get(
                f"{(base_url or DOUBAO_VIDEO_BASE_URL).rstrip('/')}/contents/generations/tasks/{task_id}",
                headers=headers,
            )
            if task_response.is_error:
                raise ValueError(f"Doubao task polling failed: {_provider_error(_response_payload(task_response))[:220]}")
            task = _response_payload(task_response)
            if not isinstance(task, dict):
                raise ValueError("Doubao task polling returned an invalid response")
            status = str(task.get("status") or "").lower()
            if status == "succeeded":
                video_url = str((task.get("content") or {}).get("video_url") or "").strip()
                if not video_url:
                    raise ValueError("Doubao task succeeded without a video URL")
                video_response = await client.get(video_url)
                video_response.raise_for_status()
                if not video_response.content:
                    raise ValueError("Doubao returned an empty video")
                return VideoResult(video_response.content)
            if status in {"failed", "expired"}:
                raise ValueError(f"Doubao video task {status}: {_provider_error(task)[:220]}")
        raise TimeoutError("Doubao video generation timed out")


async def _generate_gemini_video(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings,
    duration: int,
    reference: dict[str, Any] | None,
    base_url: str,
) -> VideoResult:
    client = genai.Client(
        api_key=api_key.strip(),
        http_options={
            "base_url": gemini_video_base_url(base_url),
            "timeout": GENERATION_TIMEOUT_SECONDS * 1000,
        },
    )
    try:
        image = None
        if reference:
            data, mime_type = parse_reference(reference)
            image = types.Image(image_bytes=data, mime_type=mime_type)
        operation = await client.aio.models.generate_videos(
            model=model,
            prompt=prompt,
            image=image,
            config=types.GenerateVideosConfig(
                number_of_videos=1,
                duration_seconds=duration,
                aspect_ratio=settings.ratio,
                resolution=settings.resolution,
            ),
        )
        deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
        while not operation.done and time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            operation = await client.aio.operations.get(operation=operation)
        if not operation.done:
            raise TimeoutError("Gemini video generation timed out")
        if operation.error:
            raise ValueError(f"Gemini video task failed: {_provider_error(operation.error)[:220]}")
        result = operation.result or operation.response
        generated_videos = result.generated_videos if result else None
        if not generated_videos or not generated_videos[0].video:
            raise ValueError("Gemini task completed without a video")
        data = await client.aio.files.download(file=generated_videos[0].video)
        if not data:
            raise ValueError("Gemini returned an empty video")
        return VideoResult(data)
    finally:
        await client.aio.aclose()


async def _generate_qwen_video(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings,
    duration: int,
    reference: dict[str, Any] | None,
    base_url: str,
) -> VideoResult:
    model = model.strip()
    validate_qwen_video_input(model, reference)
    payload: dict[str, Any] = {
        "model": model,
        "input": {"prompt": prompt},
        "parameters": {
            "resolution": settings.resolution.upper(),
            "ratio": settings.ratio,
            "duration": duration,
            "prompt_extend": True,
            "watermark": False,
        },
    }
    if reference:
        data, mime_type = parse_reference(reference)
        image_url = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
        if model.lower() == "wan2.7-i2v":
            payload["input"]["media"] = [{"type": "first_frame", "url": image_url}]
            payload["parameters"].pop("ratio")
        else:
            payload["input"]["img_url"] = image_url
    base = (base_url or QWEN_VIDEO_BASE_URL).strip().rstrip("/")
    headers = {"Authorization": f"Bearer {api_key.strip()}", "X-DashScope-Async": "enable"}
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.post(f"{base}/services/aigc/video-generation/video-synthesis", headers=headers, json=payload)
        response.raise_for_status()
        task_id = str(response.json().get("output", {}).get("task_id") or "")
        if not task_id:
            raise ValueError("Qwen video task creation returned no task id")
        deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            task_response = await client.get(f"{base}/tasks/{task_id}", headers={"Authorization": headers["Authorization"]})
            task_response.raise_for_status()
            output = task_response.json().get("output", {})
            status = str(output.get("task_status") or "").upper()
            if status == "SUCCEEDED":
                video_url = str(output.get("video_url") or "")
                if not video_url:
                    raise ValueError("Qwen video task succeeded without a video URL")
                video_response = await client.get(video_url)
                video_response.raise_for_status()
                return VideoResult(video_response.content)
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                raise ValueError(f"Qwen video task {status.lower()}: {output.get('message') or output.get('code') or ''}")
        raise TimeoutError("Qwen video generation timed out")


async def generate_video(
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    resolution: str,
    fps: int,
    duration: int,
    reference: dict[str, Any] | None = None,
    base_url: str = "",
) -> VideoResult:
    settings = resolve_video_settings(provider, resolution, fps, duration)
    if reference:
        parse_reference(reference)
    if provider == "doubao":
        return await _generate_doubao_video(api_key, model, prompt, settings, duration, reference, base_url)
    if provider == "qwen":
        return await _generate_qwen_video(api_key, model, prompt, settings, duration, reference, base_url)
    return await _generate_gemini_video(api_key, model, prompt, settings, duration, reference, base_url)
