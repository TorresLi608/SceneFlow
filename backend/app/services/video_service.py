from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
import time
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from dashscope.aigc.video_synthesis import VideoSynthesis
from dashscope.utils.oss_utils import OssUtils
from google import genai
from google.genai import types

from app.services.config_service import is_omni_video_model, normalize_provider


DOUBAO_VIDEO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
GEMINI_VIDEO_BASE_URL = "https://generativelanguage.googleapis.com"
QWEN_VIDEO_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
GROK_VIDEO_BASE_URL = "https://api.x.ai/v1"
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
# xAI documents this ratio set; `adaptive` and the 5:2-style extras the API also lists are
# deliberately not offered, because the editor and the standalone panel only speak these.
GROK_VIDEO_ASPECT_RATIOS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}


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


def external_media_url(value: dict[str, Any]) -> str | None:
    url = str(value.get("url") or "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("media URL must be a valid http(s) URL")
    return url


def media_data_url(value: dict[str, Any], kind: str) -> str:
    url = external_media_url(value)
    if url:
        return url
    if kind == "image":
        data, mime_type = parse_reference(value)
    elif kind == "video":
        data, mime_type, _ = parse_media(value, {"video/mp4", "video/quicktime", "video/webm"}, MAX_MEDIA_BYTES)
    else:
        data, mime_type, _ = parse_media(value, {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4"}, MAX_MEDIA_BYTES)
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def validate_video_inputs(
    capabilities: dict[str, Any],
    references: list[dict[str, Any]],
    reference_videos: list[dict[str, Any]],
    reference_audios: list[dict[str, Any]],
) -> None:
    references = references or []
    reference_videos = reference_videos or []
    reference_audios = reference_audios or []
    validate_video_reference_counts(capabilities, len(references), len(reference_videos), len(reference_audios))
    for reference in references:
        media_data_url(reference, "image")
    for reference_video in reference_videos:
        media_data_url(reference_video, "video")
    for reference_audio in reference_audios:
        media_data_url(reference_audio, "audio")


def validate_video_reference_counts(
    capabilities: dict[str, Any],
    image_count: int,
    video_count: int,
    audio_count: int,
) -> None:
    maximum = capabilities["maxReferenceImages"] if capabilities.get("referenceImages", capabilities["maxReferenceImages"] > 0) else 0
    if capabilities["referenceImagesRequired"] and not image_count:
        raise ValueError("selected model requires a reference image")
    if image_count > maximum:
        raise ValueError(f"selected model accepts at most {maximum} reference images")
    if video_count and not capabilities["referenceVideo"]:
        raise ValueError("selected model does not support a reference video")
    if capabilities["referenceVideosRequired"] and not video_count:
        raise ValueError("selected model requires a reference video")
    if video_count > capabilities["maxReferenceVideos"]:
        raise ValueError(f"selected model accepts at most {capabilities['maxReferenceVideos']} reference videos")
    if audio_count and not capabilities["referenceAudio"]:
        raise ValueError("selected model does not support reference audio")
    if capabilities["referenceAudiosRequired"] and not audio_count:
        raise ValueError("selected model requires reference audio")
    if audio_count > capabilities["maxReferenceAudios"]:
        raise ValueError(f"selected model accepts at most {capabilities['maxReferenceAudios']} reference audios")


def resolve_video_settings(provider: str, aspect_ratio: str, quality: str | None = None) -> VideoSettings:
    provider = normalize_provider(provider)
    if provider == "grok":
        # xAI takes the ratio and resolution directly and has no `adaptive`; anything else
        # is a config error rather than something to silently rewrite.
        settings = VIDEO_SETTINGS.get(aspect_ratio)
        if settings is None and aspect_ratio in GROK_VIDEO_ASPECT_RATIOS:
            settings = VideoSettings(quality or "720p", aspect_ratio)
        if settings is None:
            raise ValueError("unsupported video aspect ratio")
        return settings
    if provider not in {"doubao", "gemini"}:
        raise ValueError("aspect ratio is only supported for Doubao, Gemini, and Grok")
    settings = VIDEO_SETTINGS.get(aspect_ratio)
    if settings is None and aspect_ratio in {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"}:
        settings = VideoSettings(quality or "720p", aspect_ratio)
    if not settings:
        raise ValueError("unsupported video aspect ratio")
    if provider == "gemini" and settings.ratio == "1:1":
        raise ValueError("Gemini video models do not support 1:1 output")
    return settings


def resolve_qwen_video_quality(quality: str) -> str:
    normalized = quality.strip().lower()
    if normalized not in QWEN_VIDEO_QUALITIES | {"2k", "4k"}:
        raise ValueError("Qwen video quality must be 480p, 720p, 1080p, 2K, or 4K")
    return normalized


def qwen_video_family(model: str) -> str:
    """Which DashScope media contract a Qwen video model speaks.

    Kept as a family rather than a per-model table because the wire contract changed
    between generations, not between revisions: Wan 3.0 renamed the driving track to
    `reference_audio` and added the `audio` output switch, Wan 2.7 takes a timbre to
    imitate under `reference_voice`, and anything older still speaks `driving_audio`.
    """
    normalized = model.strip().lower()
    if normalized.startswith("wan3.0"):
        return "wan3"
    if normalized == "wan2.7" or normalized.startswith("wan2.7-r2v"):
        return "wan27"
    return "legacy"


def qwen_media_types(model: str) -> tuple[str, str]:
    """The `(video, audio)` media type names this model's generation expects."""
    family = qwen_video_family(model)
    if family == "wan3":
        return "reference_video", "reference_audio"
    if family == "wan27":
        return "reference_video", "reference_voice"
    return "video", "driving_audio"


def validate_qwen_video_input(model: str, references: list[dict[str, Any]], reference_videos: list[dict[str, Any]]) -> None:
    normalized = model.strip().lower()
    family = qwen_video_family(model)
    # Wan 2.7-r2v and the whole Wan 3.0 line take references by name rather than by an
    # `-i2v`-style suffix, so the suffix sniffing below only decides for older models.
    accepts_images = family in {"wan3", "wan27"} or any(part in normalized for part in ("-i2v", "-r2v", "videoedit"))
    accepts_videos = family in {"wan3", "wan27"} or "videoedit" in normalized
    if "-i2v" in normalized and not references:
        raise ValueError(f"Qwen image-to-video model {model} requires a reference image")
    if references and not accepts_images:
        raise ValueError(f"Qwen text-to-video model {model} does not accept a reference image; use wan2.7-i2v")
    if reference_videos and not accepts_videos:
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
    aspect_ratio = selected("aspectRatio", capabilities["aspectRatios"])
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
    return quality, aspect_ratio, fps, duration, prompt_extend


def supported_video_defaults(payload: dict[str, Any], capabilities: dict[str, Any]) -> dict[str, Any]:
    """Drop saved project defaults that the currently selected model cannot accept."""
    defaults = {
        name: payload[name]
        for name, capability in (("quality", "qualities"), ("aspectRatio", "aspectRatios"), ("fps", "fps"))
        if payload.get(name) in capabilities[capability]
    }
    duration = payload.get("duration")
    if isinstance(duration, int) and not isinstance(duration, bool) and capabilities["minDuration"] <= duration <= capabilities["maxDuration"]:
        defaults["duration"] = duration
    if payload.get("promptExtend") and capabilities["promptExtend"]:
        defaults["promptExtend"] = True
    return defaults


def build_doubao_payload(
    model: str,
    prompt: str,
    settings: VideoSettings | None,
    quality: str | None,
    fps: int | None,
    duration: int,
    reference: dict[str, Any] | None = None,
    output_audio: bool | None = None,
    additional_references: list[dict[str, Any]] | None = None,
    reference_videos: list[dict[str, Any]] | None = None,
    reference_audios: list[dict[str, Any]] | None = None,
    first_frame: dict[str, Any] | None = None,
    last_frame: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    images = ([reference] if reference else []) + (additional_references or [])
    for image in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": media_data_url(image, "image")},
                "role": "reference_image",
            }
        )
    if first_frame:
        content.append({"type": "image_url", "image_url": {"url": media_data_url(first_frame, "image")}, "role": "first_frame"})
    if last_frame:
        content.append({"type": "image_url", "image_url": {"url": media_data_url(last_frame, "image")}, "role": "last_frame"})
    for video in reference_videos or []:
        content.append({"type": "video_url", "video_url": {"url": media_data_url(video, "video")}, "role": "reference_video"})
    for audio in reference_audios or []:
        content.append({"type": "audio_url", "audio_url": {"url": media_data_url(audio, "audio")}, "role": "reference_audio"})
    payload: dict[str, Any] = {
        "model": model,
        "content": content,
        "duration": duration,
        "watermark": False,
    }
    # Omitted rather than defaulted: a caller with no audio switch (the standalone video
    # page) must keep getting the provider's own default, not a silent opt-in to a
    # costlier render.
    if output_audio is not None:
        payload["generate_audio"] = output_audio
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


def is_native_gemini_video_url(base_url: str = "") -> bool:
    base = (base_url or GEMINI_VIDEO_BASE_URL).strip().rstrip("/")
    # Explicit /v1beta also lets a relay opt into the native Gemini protocol.
    return (urlparse(base).hostname or "").lower() == "generativelanguage.googleapis.com" or base.endswith(("/v1beta", "/v1beta/openai"))


async def _generate_relay_video(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings | None,
    quality: str | None,
    duration: int,
    reference: dict[str, Any] | None,
    base_url: str,
    provider_label: str = "Gemini",
) -> VideoResult:
    """Sub API / New API video tasks, including the older unified task route."""
    base = base_url.strip().rstrip("/")
    if not urlparse(base).path.rstrip("/"):
        base += "/v1"
    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    metadata: dict[str, Any] = {}
    if quality:
        metadata["resolution"] = quality.lower()
    if settings:
        metadata["aspectRatio"] = settings.ratio
    payload: dict[str, Any] = {
        "model": model, "prompt": prompt, "seconds": str(duration),
        "duration": duration, "metadata": metadata,
    }
    if quality:
        payload["resolution"] = quality.lower()
    if settings:
        height = {"480p": 480, "720p": 720, "1080p": 1080, "4k": 2160}.get((quality or settings.resolution).lower())
        if height:
            width = height * 16 // 9
            payload["size"] = f"{height}x{width}" if settings.ratio == "9:16" else f"{width}x{height}"
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
        if reference:
            url = external_media_url(reference)
            if url:
                image_response = await client.get(url)
                image_response.raise_for_status()
                reference = {"data": "data:" + image_response.headers.get("content-type", "image/jpeg").split(";", 1)[0] + ";base64," + base64.b64encode(image_response.content).decode("ascii")}
            data, mime_type = parse_reference(reference)
            image = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
            # New API consumes `images`; compatible gateways also accept `image`.
            payload["images"] = [image]
            payload["image"] = image
            payload["input_reference"] = image

        endpoint = f"{base}/videos"
        response = await client.post(endpoint, headers=headers, json=payload)
        # Only a missing route permits resubmission. Never retry an accepted task or
        # provider failure: doing so could create a second billable generation.
        if response.status_code in {404, 405}:
            endpoint = f"{base}/video/generations"
            response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()

        def task_body(response: httpx.Response) -> dict[str, Any]:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError(f"{provider_label} relay returned an invalid video task")
            if isinstance(body.get("data"), dict):
                body = body["data"]
            return body

        task = task_body(response)
        task_id = str(task.get("task_id") or task.get("id") or "").strip()
        if not task_id:
            raise ValueError(f"{provider_label} relay task creation returned no task id")
        deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            status = str(task.get("status") or "").lower()
            if status in {"completed", "succeeded", "success"}:
                video = task.get("video") or {}
                video_url = task.get("url") or task.get("video_url") or task.get("result_url") or (video.get("url") if isinstance(video, dict) else None)
                # OpenAI-format task responses expose the clip at /content instead.
                download_url = urljoin(base + "/", str(video_url)) if video_url else f"{base}/videos/{quote(task_id, safe='')}/content"
                # Keep the gateway token on its own origin; CDN URLs need no token.
                download_headers = headers if urlparse(download_url)[:2] == urlparse(base)[:2] else {}
                video_response = await client.get(download_url, headers=download_headers)
                video_response.raise_for_status()
                if not video_response.content:
                    raise ValueError(f"{provider_label} relay returned an empty video")
                return VideoResult(video_response.content)
            if status in {"failed", "failure", "error", "canceled", "cancelled", "expired"}:
                raise ValueError(f"{provider_label} relay video task {status}: {_provider_error(task.get('error') or task.get('fail_reason') or status)[:220]}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            response = await client.get(f"{endpoint}/{quote(task_id, safe='')}", headers=headers)
            response.raise_for_status()
            task = task_body(response)
        raise TimeoutError(f"{provider_label} relay video generation timed out")


def grok_video_base_url(base_url: str = "") -> str:
    """The xAI video base: normalize only the official host, keep relays untouched."""
    base = (base_url or GROK_VIDEO_BASE_URL).strip().rstrip("/")
    parsed = urlparse(base)
    if (parsed.hostname or "").lower() == "api.x.ai" and not parsed.path.rstrip("/").endswith("/v1"):
        return f"{base}/v1"
    return base


def is_native_qwen_video_url(base_url: str) -> bool:
    return (urlparse(base_url or QWEN_VIDEO_BASE_URL).hostname or "").lower() == "dashscope.aliyuncs.com"


def qwen_media_policy_model(model: str) -> str:
    return {"wan2.5-i2v": "wan2.6-i2v", "wan2.7-i2v": "wan2.6-i2v", "wan2.7-r2v": "wan2.6-r2v"}.get(
        model.strip().lower(), model.strip()
    )


def _sdk_value(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        result = getattr(value, name, None)
        if result is not None:
            return result
    return None


def _sdk_error(value: Any) -> str:
    return str(_sdk_value(value, "message", "code", "error") or value)


async def _generate_doubao_video_sdk(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings | None,
    quality: str | None,
    fps: int | None,
    duration: int,
    reference: dict[str, Any] | None,
    base_url: str,
    output_audio: bool | None = None,
    additional_references: list[dict[str, Any]] | None = None,
    reference_videos: list[dict[str, Any]] | None = None,
    reference_audios: list[dict[str, Any]] | None = None,
    first_frame: dict[str, Any] | None = None,
    last_frame: dict[str, Any] | None = None,
) -> VideoResult:
    try:
        from volcenginesdkarkruntime import Ark
    except ImportError as exc:
        raise RuntimeError("volcengine-python-sdk[ark] is required for Doubao video generation") from exc

    payload = build_doubao_payload(
        model, prompt, settings, quality, fps, duration, reference, output_audio,
        additional_references, reference_videos, reference_audios, first_frame, last_frame,
    )
    # Ark's official task schema has no fps field; the model uses its service default.
    payload.pop("fps", None)
    client = Ark(api_key=api_key.strip(), base_url=(base_url or DOUBAO_VIDEO_BASE_URL).rstrip("/"))
    create = await asyncio.to_thread(client.content_generation.tasks.create, **payload)
    task_id = str(_sdk_value(create, "id", "task_id") or "").strip()
    if not task_id:
        raise ValueError(f"Doubao task creation returned no task id: {_sdk_error(create)[:180]}")

    deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        task = await asyncio.to_thread(client.content_generation.tasks.get, task_id=task_id)
        status = str(_sdk_value(task, "status", "task_status") or "").lower()
        if status in {"succeeded", "success", "completed"}:
            content = _sdk_value(task, "content") or {}
            video_url = str(_sdk_value(content, "video_url", "videoUrl", "url") or "").strip()
            if not video_url:
                raise ValueError("Doubao task succeeded without a video URL")
            async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as http:
                response = await http.get(video_url)
                response.raise_for_status()
                if not response.content:
                    raise ValueError("Doubao returned an empty video")
                return VideoResult(response.content)
        if status in {"failed", "expired", "canceled", "cancelled"}:
            raise ValueError(f"Doubao video task {status}: {_sdk_error(task)[:220]}")
    raise TimeoutError("Doubao video generation timed out")


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
    output_audio: bool | None = None,
    additional_references: list[dict[str, Any]] | None = None,
    reference_videos: list[dict[str, Any]] | None = None,
    reference_audios: list[dict[str, Any]] | None = None,
    first_frame: dict[str, Any] | None = None,
    last_frame: dict[str, Any] | None = None,
) -> VideoResult:
    return await _generate_doubao_video_sdk(
        api_key, model, prompt, settings, quality, fps, duration, reference, base_url, output_audio,
        additional_references, reference_videos, reference_audios, first_frame, last_frame,
    )


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
    if not is_native_gemini_video_url(base_url):
        return await _generate_relay_video(api_key, model, prompt, settings, quality, duration, reference, base_url)
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
            reference_url = external_media_url(reference)
            if reference_url:
                async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as http:
                    response = await http.get(reference_url)
                    response.raise_for_status()
                    data = response.content
                    mime_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
                if mime_type not in {"image/png", "image/jpeg", "image/webp"} or not data or len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("reference image URL must point to a PNG, JPEG, or WebP image under 10MB")
            else:
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
                # Gemini Developer API rejects fps even when it is 24. Older saved
                # configurations may still declare it; leave the provider default.
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
        video = generated_videos[0].video
        data = video.video_bytes or await client.aio.files.download(file=video)
        if not data:
            raise ValueError("Gemini returned an empty video")
        return VideoResult(data)
    finally:
        await client.aio.aclose()


async def _generate_omni_video(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings | None,
    quality: str | None,
    duration: int,
    reference: dict[str, Any] | None,
    base_url: str,
    *,
    first_frame: bool = False,
) -> VideoResult:
    """Omni uses Interactions on Google and video tasks on compatible gateways."""
    if not is_native_gemini_video_url(base_url):
        return await _generate_relay_video(api_key, model, prompt, settings, quality, duration, reference, base_url, "Gemini Omni")
    if not 3 <= duration <= 10:
        raise ValueError("Gemini Omni video duration must be between 3 and 10 seconds")
    if quality and quality.lower() not in {"720p", "1080p", "4k"}:
        raise ValueError("Gemini Omni video quality must be 720p, 1080p, or 4K")
    base = gemini_video_base_url(base_url) + "/v1beta"
    headers = {"x-goog-api-key": api_key.strip()}
    response_format: dict[str, Any] = {"type": "video", "delivery": "uri", "duration": f"{duration}s"}
    if settings:
        response_format["aspect_ratio"] = settings.ratio
    if quality:
        response_format["resolution"] = quality.lower()
    try:
        async with asyncio.timeout(GENERATION_TIMEOUT_SECONDS), httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=False) as client:
            inputs: str | list[dict[str, Any]] = prompt
            if reference:
                url = external_media_url(reference)
                if url:
                    image_response = await client.get(url, follow_redirects=True)
                    image_response.raise_for_status()
                    reference = {"data": "data:" + image_response.headers.get("content-type", "image/jpeg").split(";", 1)[0] + ";base64," + base64.b64encode(image_response.content).decode("ascii")}
                data, mime_type = parse_reference(reference)
                # A reference and an explicit first frame have different roles in
                # Omni. Only the frame slot pins the opening shot.
                role = "[# Sources <FIRST_FRAME>@Image1]" if first_frame else "[# References <IMAGE_REF_0>@Image1]"
                inputs = [
                    {"type": "image", "mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")},
                    {"type": "text", "text": f"{role}\n{prompt}"},
                ]
            # Use REST: the installed Gen AI SDK's VideoResponseFormat lacks the
            # documented resolution field and can discard it during serialization.
            response = await client.post(f"{base}/interactions", headers=headers, json={
                "model": model, "input": inputs, "response_format": response_format,
                "background": False, "store": False, "stream": False,
            })
            response.raise_for_status()
            interaction = response.json()
            if not isinstance(interaction, dict):
                raise ValueError("Gemini Omni returned an invalid interaction")
            status = str(interaction.get("status") or "").lower()
            if status != "completed" or interaction.get("error"):
                raise ValueError(f"Gemini Omni interaction {status or 'incomplete'}: {_provider_error(interaction.get('error') or status)[:220]}")
            video = next((
                content for step in interaction.get("steps", []) if step.get("type") == "model_output"
                for content in step.get("content", []) if content.get("type") == "video"
            ), interaction.get("output_video") or {})
            if video.get("data"):
                try:
                    data = base64.b64decode(video["data"], validate=True)
                except (ValueError, TypeError) as exc:
                    raise ValueError("Gemini Omni returned invalid video data") from exc
            elif video.get("uri"):
                uri = str(video["uri"])
                file_match = re.search(r"(?:^|/)files/([^/:?]+)", urlparse(uri).path)
                is_google_file = not urlparse(uri).netloc or urlparse(uri).netloc in {
                    urlparse(base).netloc, "generativelanguage.googleapis.com",
                }
                if file_match and is_google_file:
                    file_path = f"{base}/files/{quote(file_match.group(1), safe='')}"
                    while True:
                        file_response = await client.get(file_path, headers=headers)
                        file_response.raise_for_status()
                        file = file_response.json()
                        state = str(file.get("state") or "").upper()
                        if state == "ACTIVE":
                            break
                        if state == "FAILED":
                            raise ValueError("Gemini Omni generated video processing failed")
                        await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    uri = f"{file_path}:download?alt=media"
                else:
                    uri = urljoin(base + "/", uri)
                # httpx strips Authorization on cross-origin redirects, but does
                # not strip x-goog-api-key. Recheck the origin on every hop.
                for _ in range(6):
                    download_headers = headers if urlparse(uri)[:2] == urlparse(base)[:2] else {}
                    video_response = await client.get(uri, headers=download_headers)
                    if video_response.is_redirect and video_response.headers.get("location"):
                        uri = urljoin(uri, video_response.headers["location"])
                        continue
                    video_response.raise_for_status()
                    data = video_response.content
                    break
                else:
                    raise ValueError("Gemini Omni video download has too many redirects")
            else:
                raise ValueError("Gemini Omni interaction completed without a video")
            if not data:
                raise ValueError("Gemini Omni returned an empty video")
            return VideoResult(data)
    except TimeoutError as exc:
        raise TimeoutError("Gemini Omni video generation timed out") from exc


async def _generate_qwen_video(
    api_key: str,
    model: str,
    prompt: str,
    quality: str,
    duration: int,
    prompt_extend: bool,
    references: list[dict[str, Any]],
    reference_videos: list[dict[str, Any]],
    reference_audios: list[dict[str, Any]],
    base_url: str,
    aspect_ratio: str | None = None,
    output_audio: bool | None = None,
    first_frame: dict[str, Any] | None = None,
    last_frame: dict[str, Any] | None = None,
) -> VideoResult:
    references = references or []
    reference_videos = reference_videos or []
    reference_audios = reference_audios or []
    model = model.strip()
    validate_qwen_video_input(model, references, reference_videos)
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
    if aspect_ratio:
        payload["parameters"]["ratio"] = aspect_ratio
    base = (base_url or QWEN_VIDEO_BASE_URL).strip().rstrip("/")
    headers = {"Authorization": f"Bearer {api_key.strip()}", "X-DashScope-Async": "enable"}
    if is_native_qwen_video_url(base):
        return await _generate_qwen_video_sdk(
            api_key, model, prompt, quality, duration, prompt_extend,
            references, reference_videos, reference_audios, base, aspect_ratio, output_audio, first_frame, last_frame,
        )
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
        media: list[dict[str, str]] = []
        normalized_model = model.lower()
        video_type, audio_type = qwen_media_types(model)
        if "-r2v" in normalized_model and qwen_video_family(model) == "legacy":
            payload["input"]["reference_image_urls"] = [media_data_url(item, "image") for item in references]
        else:
            if first_frame:
                media.append({"type": "first_frame", "url": media_data_url(first_frame, "image")})
            if last_frame:
                media.append({"type": "last_frame", "url": media_data_url(last_frame, "image")})
            if references:
                for item in references:
                    media.append({"type": "reference_image", "url": media_data_url(item, "image")})
            for reference_video in reference_videos:
                media.append({"type": video_type, "url": media_data_url(reference_video, "video")})
            for reference_audio in reference_audios:
                media.append({"type": audio_type, "url": media_data_url(reference_audio, "audio")})
            if media:
                payload["input"]["media"] = media
        # Only Wan 3.0 generates its own track; the older families are fed one instead, so
        # there is no switch to send them.
        if output_audio is not None and qwen_video_family(model) == "wan3":
            payload["parameters"]["audio"] = output_audio
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
    reference_videos: list[dict[str, Any]],
    reference_audios: list[dict[str, Any]],
    base: str,
    aspect_ratio: str | None = None,
    output_audio: bool | None = None,
    first_frame: dict[str, Any] | None = None,
    last_frame: dict[str, Any] | None = None,
) -> VideoResult:
    references = references or []
    reference_videos = reference_videos or []
    reference_audios = reference_audios or []
    temp_files: list[str] = []
    media: list[dict[str, str]] = []

    async def upload(value: dict[str, Any], kind: str) -> str:
        url = external_media_url(value)
        if url:
            return url
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
        video_type, audio_type = qwen_media_types(model)
        if "-r2v" in model.lower() and qwen_video_family(model) == "legacy":
            input_data: dict[str, Any] = {"reference_image_urls": [await upload(item, "image") for item in references]}
        else:
            if first_frame:
                media.append({"type": "first_frame", "url": await upload(first_frame, "image")})
            if last_frame:
                media.append({"type": "last_frame", "url": await upload(last_frame, "image")})
            for item in references:
                media.append({"type": "reference_image", "url": await upload(item, "image")})
            for reference_video in reference_videos:
                media.append({"type": video_type, "url": await upload(reference_video, "video")})
            for reference_audio in reference_audios:
                media.append({"type": audio_type, "url": await upload(reference_audio, "audio")})
            input_data = {"media": media} if media else {}
        # See the HTTP branch: only Wan 3.0 has an output-audio switch to pass through.
        extra = {"audio": output_audio} if output_audio is not None and qwen_video_family(model) == "wan3" else {}
        task = await asyncio.to_thread(
            VideoSynthesis.async_call,
            model=model, prompt=prompt, extra_input=input_data, api_key=api_key.strip(), duration=duration,
            prompt_extend=prompt_extend, watermark=False, resolution=quality.upper() if quality else None,
            ratio=aspect_ratio, **extra,
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
        status = str(_sdk_value(output, "task_status", "status") or "").upper()
        if status and status != "SUCCEEDED":
            raise ValueError(
                f"Qwen video task {status.lower()}: "
                f"{_sdk_value(output, 'message', 'code') or ''}"
            )
        video_url = str(_sdk_value(output, "video_url", "videoUrl", "url") or "")
        if not video_url:
            raise ValueError("Qwen video task succeeded without a video URL")
        async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
            video_response = await client.get(video_url)
            video_response.raise_for_status()
            return VideoResult(video_response.content)
    finally:
        for path in temp_files:
            Path(path).unlink(missing_ok=True)


async def _generate_grok_video(
    api_key: str,
    model: str,
    prompt: str,
    settings: VideoSettings | None,
    quality: str | None,
    duration: int,
    references: list[dict[str, Any]],
    base_url: str,
    output_audio: bool | None = None,
    first_frame: dict[str, Any] | None = None,
    last_frame: dict[str, Any] | None = None,
) -> VideoResult:
    """xAI's asynchronous video API: submit a task, poll the request id, download the clip.

    `image` pins the first frame; additional stills ride as `reference_images`, which is
    the reference-to-video input. Reference videos and audios are not part of this
    contract, and the capability defaults declare them unsupported.
    """
    payload: dict[str, Any] = {"model": model.strip(), "prompt": prompt, "duration": duration}
    if settings:
        payload["aspect_ratio"] = settings.ratio
    if quality:
        payload["resolution"] = quality
    if output_audio is not None:
        payload["generate_audio"] = output_audio
    if first_frame:
        payload["image"] = media_data_url(first_frame, "image")
    if last_frame:
        payload["last_frame"] = media_data_url(last_frame, "image")
    if references:
        payload["reference_images"] = [media_data_url(item, "image") for item in references]

    base = grok_video_base_url(base_url)
    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    async with httpx.AsyncClient(timeout=GENERATION_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.post(f"{base}/videos/generations", headers=headers, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"provider status {exc.response.status_code}: {exc.response.text.strip()[:220]}") from exc
        request_id = str(response.json().get("request_id") or "").strip()
        if not request_id:
            raise ValueError("Grok video task creation returned no request id")
        deadline = time.monotonic() + GENERATION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            task_response = await client.get(f"{base}/videos/{request_id}", headers=headers)
            task_response.raise_for_status()
            task = task_response.json()
            status = str(task.get("status") or "").lower()
            if status in {"done", "completed", "succeeded"}:
                video_url = str((task.get("video") or {}).get("url") or "").strip()
                if not video_url:
                    raise ValueError("Grok video task succeeded without a video URL")
                video_response = await client.get(video_url)
                video_response.raise_for_status()
                if not video_response.content:
                    raise ValueError("Grok returned an empty video")
                return VideoResult(video_response.content)
            if status in {"failed", "error", "canceled", "cancelled", "expired"}:
                raise ValueError(f"Grok video task {status}: {_provider_error(task.get('error') or task)[:220]}")
        raise TimeoutError("Grok video generation timed out")


async def generate_video(
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
    aspect_ratio: str | None,
    fps: int | None,
    duration: int,
    quality: str | None = None,
    prompt_extend: bool = False,
    references: list[dict[str, Any]] | None = None,
    reference_video: dict[str, Any] | None = None,
    driving_audio: dict[str, Any] | None = None,
    reference_videos: list[dict[str, Any]] | None = None,
    reference_audios: list[dict[str, Any]] | None = None,
    base_url: str = "",
    output_audio: bool | None = None,
    first_frame: dict[str, Any] | None = None,
    last_frame: dict[str, Any] | None = None,
) -> VideoResult:
    provider = normalize_provider(provider)
    references = references or []
    reference_videos = reference_videos or ([reference_video] if reference_video else [])
    reference_audios = reference_audios or ([driving_audio] if driving_audio else [])
    if provider == "qwen":
        return await _generate_qwen_video(
            api_key, model, prompt, quality or "", duration, prompt_extend, references, reference_videos, reference_audios, base_url,
            aspect_ratio, output_audio, first_frame, last_frame,
        )
    if provider == "grok":
        settings = resolve_video_settings(provider, aspect_ratio, quality) if aspect_ratio else None
        return await _generate_grok_video(
            api_key, model, prompt, settings, quality, duration, references, base_url, output_audio, first_frame, last_frame,
        )
    reference = references[0] if references else None
    settings = resolve_video_settings(provider, aspect_ratio, quality) if aspect_ratio else None
    if provider == "doubao":
        return await _generate_doubao_video(
            api_key, model, prompt, settings, quality, fps, duration, reference, base_url, output_audio,
            references[1:], reference_videos, reference_audios, first_frame, last_frame,
        )
    if provider == "gemini":
        if len(references) > 1 or (first_frame and references):
            raise ValueError("Gemini video accepts one reference image or one first frame")
        if last_frame or reference_videos or reference_audios:
            raise ValueError("Gemini video task adapter does not support last frames, reference videos, or reference audio")
        if is_omni_video_model(model):
            if settings and settings.ratio not in {"16:9", "9:16"}:
                raise ValueError("Gemini Omni video only supports 16:9 or 9:16 output")
            return await _generate_omni_video(
                api_key, model, prompt, settings, quality, duration, first_frame or reference,
                base_url, first_frame=bool(first_frame),
            )
        return await _generate_gemini_video(api_key, model, prompt, settings, quality, fps, duration, first_frame or reference, base_url)
    raise ValueError(f"unsupported video provider: {provider}")
