from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from dashscope.aigc.video_synthesis import VideoSynthesis
from dashscope.utils.oss_utils import OssUtils
from google import genai
from google.genai import types


DOUBAO_VIDEO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
GEMINI_VIDEO_BASE_URL = "https://generativelanguage.googleapis.com"
QWEN_VIDEO_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DATA_URL_RE = re.compile(r"^data:([^;,]+);base64,(.+)$", re.DOTALL)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_MEDIA_BYTES = 50 * 1024 * 1024
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
QWEN_VIDEO_QUALITIES = {"480p", "720p", "1080p"}


def parse_media(value: dict[str, Any], allowed: set[str], maximum: int) -> tuple[bytes, str, str]:
    match = DATA_URL_RE.match(str(value.get("data") or ""))
    if not match:
        raise ValueError("media must be a base64 data URL")
    mime_type, encoded = match.groups()
    if mime_type not in allowed:
        raise ValueError(f"unsupported media type: {mime_type}")
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("invalid reference image data") from exc
    if not data or len(data) > maximum:
        raise ValueError(f"media must be 1 byte to {maximum // (1024 * 1024)}MB")
    return data, "image/jpeg" if mime_type in {"image/jpeg", "image/jpg"} else mime_type, Path(str(value.get("name") or "media")).name


def parse_reference(value: dict[str, Any]) -> tuple[bytes, str]:
    data, mime_type, _ = parse_media(value, {"image/png", "image/jpeg", "image/jpg", "image/webp"}, MAX_IMAGE_BYTES)
    return data, mime_type


def validate_video_inputs(
    capabilities: dict[str, Any],
    references: list[dict[str, Any]],
    reference_video: dict[str, Any] | None,
    driving_audio: dict[str, Any] | None,
) -> None:
    maximum = capabilities["maxReferenceImages"]
    if capabilities["referenceImagesRequired"] and not references:
        raise ValueError("selected model requires a reference image")
    if len(references) > maximum:
        raise ValueError(f"selected model accepts at most {maximum} reference images")
    if reference_video and not capabilities["referenceVideo"]:
        raise ValueError("selected model does not support a reference video")
    if driving_audio and not capabilities["drivingAudio"]:
        raise ValueError("selected model does not support driving audio")
    for reference in references:
        parse_reference(reference)
    if reference_video:
        parse_media(reference_video, {"video/mp4", "video/quicktime", "video/webm"}, MAX_MEDIA_BYTES)
    if driving_audio:
        parse_media(driving_audio, {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4"}, MAX_MEDIA_BYTES)


def resolve_video_settings(provider: str, resolution: str) -> VideoSettings:
    provider = provider.strip().lower()
    if provider not in {"doubao", "gemini"}:
        raise ValueError("pixel resolution is only supported for Doubao and Gemini")
    settings = VIDEO_SETTINGS.get(resolution)
    if not settings:
        raise ValueError("unsupported video resolution")
    if provider == "gemini" and settings.ratio == "1:1":
        raise ValueError("Gemini video models do not support 1:1 output")
    return settings


def resolve_qwen_video_quality(quality: str) -> str:
    normalized = quality.strip().lower()
    if normalized not in QWEN_VIDEO_QUALITIES:
        raise ValueError("Qwen video quality must be 480p, 720p, or 1080p")
    return normalized


def validate_qwen_video_input(model: str, references: list[dict[str, Any]], reference_video: dict[str, Any] | None) -> None:
    normalized = model.strip().lower()
    is_i2v = "-i2v" in normalized
    if is_i2v and not references:
        raise ValueError(f"Qwen image-to-video model {model} requires a reference image")
    if references and not any(part in normalized for part in ("-i2v", "-r2v", "videoedit")):
        raise ValueError(f"Qwen text-to-video model {model} does not accept a reference image; use wan2.7-i2v")
    if reference_video and "videoedit" not in normalized:
        raise ValueError(f"Qwen model {model} does not accept a reference video")


def resolve_video_options(payload: dict[str, Any], capabilities: dict[str, Any]) -> tuple[str | None, str | None, int | None, int, bool]:
    raw_duration = payload.get("duration", capabilities["minDuration"])
    duration = int(raw_duration)
    if isinstance(raw_duration, bool) or str(duration) != str(raw_duration):
        raise ValueError("duration must be an integer")
    if not capabilities["minDuration"] <= duration <= capabilities["maxDuration"]:
        raise ValueError(f"duration must be between {capabilities['minDuration']} and {capabilities['maxDuration']} seconds")

    def selected(name: str, allowed: list[Any]) -> Any:
        value = payload.get(name)
        if not allowed:
            if value is not None:
                raise ValueError(f"selected model does not support {name}")
            return None
        value = allowed[0] if value is None else value
        if value not in allowed:
            raise ValueError(f"selected model does not support {name}={value}")
        return value

    quality = selected("quality", capabilities["qualities"])
    resolution = selected("resolution", capabilities["resolutions"])
    fps_value = payload.get("fps")
    fps = capabilities["fps"][0] if capabilities["fps"] else None
    if fps_value is not None:
        fps = int(fps_value)
        if fps not in capabilities["fps"]:
            raise ValueError(f"selected model does not support fps={fps}")
    prompt_extend = payload.get("promptExtend", False)
    if not isinstance(prompt_extend, bool):
        raise ValueError("promptExtend must be boolean")
    if prompt_extend and not capabilities["promptExtend"]:
        raise ValueError("selected model does not support promptExtend")
    return quality, resolution, fps, duration, prompt_extend


def build_doubao_payload(
    model: str,
    prompt: str,
    settings: VideoSettings | None,
    quality: str | None,
    fps: int | None,
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
    payload: dict[str, Any] = {
        "model": model,
        "content": content,
        "duration": duration,
        "watermark": False,
    }
    if settings:
        payload["ratio"] = settings.ratio
    if quality or settings:
        payload["resolution"] = quality or settings.resolution
    if fps is not None:
        payload["fps"] = fps
    return payload


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


def is_native_qwen_video_url(base_url: str) -> bool:
    return (urlparse(base_url or QWEN_VIDEO_BASE_URL).hostname or "").lower() == "dashscope.aliyuncs.com"


def qwen_media_policy_model(model: str) -> str:
    return {"wan2.5-i2v": "wan2.6-i2v", "wan2.7-i2v": "wan2.6-i2v", "wan2.7-r2v": "wan2.6-r2v"}.get(
        model.strip().lower(), model.strip()
    )


async def _generate_doubao_video(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings | None,
    quality: str | None,
    fps: int | None,
    duration: int,
    reference: dict[str, Any] | None,
    base_url: str,
) -> VideoResult:
    payload = build_doubao_payload(model, prompt, settings, quality, fps, duration, reference)
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
    settings: VideoSettings | None,
    quality: str | None,
    fps: int | None,
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
                aspect_ratio=settings.ratio if settings else None,
                resolution=quality or (settings.resolution if settings else None),
                fps=fps,
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
    quality: str,
    duration: int,
    prompt_extend: bool,
    references: list[dict[str, Any]],
    reference_video: dict[str, Any] | None,
    driving_audio: dict[str, Any] | None,
    base_url: str,
) -> VideoResult:
    model = model.strip()
    validate_qwen_video_input(model, references, reference_video)
    payload: dict[str, Any] = {
        "model": model,
        "input": {"prompt": prompt},
        "parameters": {
            "duration": duration,
            "prompt_extend": prompt_extend,
            "watermark": False,
        },
    }
    if quality:
        payload["parameters"]["resolution"] = resolve_qwen_video_quality(quality).upper()
    base = (base_url or QWEN_VIDEO_BASE_URL).strip().rstrip("/")
    headers = {"Authorization": f"Bearer {api_key.strip()}", "X-DashScope-Async": "enable"}
    if is_native_qwen_video_url(base):
        return await _generate_qwen_video_sdk(
            api_key, model, prompt, quality, duration, prompt_extend,
            references, reference_video, driving_audio, base,
        )
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
        async def media_url(value: dict[str, Any], kind: str) -> str:
            if kind == "image":
                data, mime_type = parse_reference(value)
            elif kind == "video":
                data, mime_type, _ = parse_media(value, {"video/mp4", "video/quicktime", "video/webm"}, MAX_MEDIA_BYTES)
            else:
                data, mime_type, _ = parse_media(value, {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4"}, MAX_MEDIA_BYTES)
            return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"

        media: list[dict[str, str]] = []
        normalized_model = model.lower()
        if "-r2v" in normalized_model:
            payload["input"]["reference_image_urls"] = [await media_url(item, "image") for item in references]
        else:
            if references:
                media.append({"type": "first_frame", "url": await media_url(references[0], "image")})
                for item in references[1:]:
                    media.append({"type": "reference_image", "url": await media_url(item, "image")})
            if reference_video:
                media.append({"type": "video", "url": await media_url(reference_video, "video")})
            if driving_audio:
                media.append({"type": "driving_audio", "url": await media_url(driving_audio, "audio")})
            if media:
                payload["input"]["media"] = media
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


async def _generate_qwen_video_sdk(
    api_key: str,
    model: str,
    prompt: str,
    quality: str,
    duration: int,
    prompt_extend: bool,
    references: list[dict[str, Any]],
    reference_video: dict[str, Any] | None,
    driving_audio: dict[str, Any] | None,
    base: str,
) -> VideoResult:
    temp_files: list[str] = []
    media: list[dict[str, str]] = []

    async def upload(value: dict[str, Any], kind: str) -> str:
        if kind == "image":
            data, mime_type = parse_reference(value)
            filename = Path(str(value.get("name") or "reference.png")).name
        elif kind == "video":
            data, mime_type, filename = parse_media(value, {"video/mp4", "video/quicktime", "video/webm"}, MAX_MEDIA_BYTES)
        else:
            data, mime_type, filename = parse_media(value, {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4"}, MAX_MEDIA_BYTES)
        suffix = Path(filename).suffix or "." + mime_type.split("/", 1)[-1].replace("jpeg", "jpg")
        temp = tempfile.NamedTemporaryFile(prefix="sceneflow-qwen-", suffix=suffix, delete=False)
        temp.write(data)
        temp.close()
        temp_files.append(temp.name)
        result = await asyncio.to_thread(
            OssUtils.upload,
            model=qwen_media_policy_model(model),
            file_path=temp.name,
            api_key=api_key.strip(),
            base_address=base,
        )
        return result[0]

    try:
        if "-r2v" in model.lower():
            input_data: dict[str, Any] = {"reference_image_urls": [await upload(item, "image") for item in references]}
        else:
            for index, item in enumerate(references):
                media.append({"type": "first_frame" if index == 0 else "reference_image", "url": await upload(item, "image")})
            if reference_video:
                media.append({"type": "video", "url": await upload(reference_video, "video")})
            if driving_audio:
                media.append({"type": "driving_audio", "url": await upload(driving_audio, "audio")})
            input_data = {"media": media} if media else {}
        task = await asyncio.to_thread(
            VideoSynthesis.async_call,
            model=model, prompt=prompt, extra_input=input_data, api_key=api_key.strip(), duration=duration,
            prompt_extend=prompt_extend, watermark=False, resolution=quality.upper() if quality else None,
            headers={"X-DashScope-OssResourceResolve": "enable"} if media or "reference_image_urls" in input_data else {}, base_address=base,
        )
        if getattr(task, "status_code", 200) != 200:
            raise ValueError(f"Qwen video task creation failed: {getattr(task, 'message', '') or getattr(task, 'code', '')}")
        result = await asyncio.to_thread(
            VideoSynthesis.wait, task, api_key=api_key.strip(), wait_timeout=GENERATION_TIMEOUT_SECONDS
        )
        if getattr(result, "status_code", 200) != 200:
            raise ValueError(f"Qwen video task failed: {getattr(result, 'message', '') or getattr(result, 'code', '')}")
        output = getattr(result, "output", None) or {}
        status = str(output.get("task_status") or "").upper()
        if status and status != "SUCCEEDED":
            raise ValueError(f"Qwen video task {status.lower()}: {output.get('message') or output.get('code') or ''}")
        video_url = str((output.get("video_url") if hasattr(output, "get") else getattr(output, "video_url", "")) or "")
        if not video_url:
            raise ValueError("Qwen video task succeeded without a video URL")
        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
            video_response = await client.get(video_url)
            video_response.raise_for_status()
            return VideoResult(video_response.content)
    finally:
        for path in temp_files:
            Path(path).unlink(missing_ok=True)


async def generate_video(
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    resolution: str | None,
    fps: int | None,
    duration: int,
    quality: str | None = None,
    prompt_extend: bool = False,
    references: list[dict[str, Any]] | None = None,
    reference_video: dict[str, Any] | None = None,
    driving_audio: dict[str, Any] | None = None,
    base_url: str = "",
) -> VideoResult:
    references = references or []
    if provider == "qwen":
        return await _generate_qwen_video(
            api_key, model, prompt, quality or "", duration, prompt_extend, references, reference_video, driving_audio, base_url
        )
    reference = references[0] if references else None
    settings = resolve_video_settings(provider, resolution) if resolution else None
    if provider == "doubao":
        return await _generate_doubao_video(api_key, model, prompt, settings, quality, fps, duration, reference, base_url)
    return await _generate_gemini_video(api_key, model, prompt, settings, quality, fps, duration, reference, base_url)
