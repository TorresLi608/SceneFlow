"""Offline checks for the pure skill boundary; no application/provider imports."""

from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
from decimal import Decimal

from pydantic import SecretStr, ValidationError

from app.skills import BaseSkill, MediaArtifact, SkillExecutionError, SkillResult, create_registry
from app.skills.base import SkillUsage
from app.skills.image_generation import ImageGenerationInput, ImageGenerationOutput
from app.skills.image_generation.schema import GeneratedImage
from app.skills.registry import SkillRegistry
from app.skills.script_breakdown import ScriptBreakdownOutput
from app.skills.storyboard_composer import StoryboardComposerInput, StoryboardComposerOutput
from app.skills.video_generation import VideoGenerationInput, VideoGenerationOutput
from app.skills.voice_design import VoiceDesignInput


MODEL = {"provider": "test", "model": "offline"}
IMAGE = {"mediaType": "image/png", "data": b"\x00\xffimage"}
AUDIO = {"mediaType": "audio/wav", "data": b"audio"}
VIDEO = {"mediaType": "video/mp4", "data": b"video"}


def rejected(model, payload) -> None:
    try:
        model.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError(f"invalid input accepted by {model.__name__}")


def test_core_import_isolation() -> None:
    # A fresh process catches indirect imports through router/config/usage services.
    script = '''
import importlib.abc
import sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        roots = ("fastapi", "sqlmodel", "sqlalchemy", "langchain", "langchain_core", "langgraph", "mcp")
        if fullname.split(".")[0] in roots or fullname.startswith(("app.core", "app.models", "app.services", "app.llms", "app.api", "app.schemas")):
            raise AssertionError("forbidden core dependency: " + fullname)
sys.meta_path.insert(0, Guard())
from app.skills import create_registry
registry = create_registry()
assert len(registry.list_metadata(implemented_only=False)) == 5
assert registry.list_metadata() == []
'''
    subprocess.run([sys.executable, "-c", script], check=True)


def test_contracts() -> None:
    media = MediaArtifact.model_validate(IMAGE)
    assert MediaArtifact.model_validate_json(media.model_dump_json()).data == IMAGE["data"]
    rejected(MediaArtifact, {"mediaType": "image/png"})
    rejected(MediaArtifact, {**IMAGE, "url": "https://example.com/image.png"})
    rejected(MediaArtifact, {"mediaType": "image/png", "url": "file:///private/file"})
    rejected(MediaArtifact, {"mediaType": "image/png", "url": "https://key@example.com/image"})
    rejected(ImageGenerationInput, {"model": MODEL, "prompt": " "})
    rejected(ImageGenerationInput, {"model": MODEL, "prompt": "frame", "userId": 1})
    rejected(ImageGenerationInput, {"model": MODEL, "prompt": "frame", "apiKey": "secret"})
    rejected(ImageGenerationInput, {"model": MODEL, "prompt": "frame", "references": [AUDIO]})
    rejected(ImageGenerationInput, {"model": MODEL, "prompt": "frame", "width": 1024})
    rejected(ImageGenerationInput, {"model": MODEL, "prompt": "frame", "frameCount": 9})
    rejected(ImageGenerationInput, {"model": MODEL, "prompt": "frame", "outputFormat": "gif", "frameDurationMs": 25})
    rejected(VideoGenerationInput, {"model": MODEL, "prompt": "frame", "durationMs": True})
    rejected(VideoGenerationInput, {"model": MODEL, "prompt": "frame", "durationMs": 4000, "lastFrame": IMAGE})
    video = VideoGenerationInput(model=MODEL, prompt="frame", duration_ms=4000, first_frame=IMAGE)
    assert video.fps is None and video.last_frame is None and video.reference_images == []
    rejected(VoiceDesignInput, {"model": MODEL, "mode": "clone"})
    rejected(VoiceDesignInput, {"model": MODEL, "mode": "synthesize", "lines": [{"key": "line", "text": "hello"}]})
    rejected(ScriptBreakdownOutput, {
        "characters": [], "scenes": [], "props": [],
        "shots": [{"key": "shot", "sceneKey": "missing", "visualPrompt": "frame", "durationMs": 4000}],
    })
    shot = {"key": "shot", "visual": IMAGE, "durationMs": 4000}
    rejected(StoryboardComposerInput, {"title": "episode", "shots": [shot, shot]})
    rejected(StoryboardComposerInput, {
        "title": "episode", "shots": [{**shot, "subtitles": [{"text": "hello", "startMs": 0, "endMs": 5000}]}],
    })
    rejected(StoryboardComposerOutput, {
        "title": "episode", "width": 1080, "height": 1920, "fps": 24,
        "durationMs": 4000, "timeline": [{**shot, "startMs": 200}],
    })
    rejected(SkillResult[ImageGenerationOutput], {"status": "success"})
    rejected(SkillResult[ImageGenerationOutput], {"status": "error"})
    usage = SkillUsage(provider="test", model="offline", quantity=Decimal("0.125"), unit="second")
    assert '"quantity":"0.125"' in usage.model_dump_json()
    assert usage.input_tokens is None


class OfflineImageSkill(BaseSkill[ImageGenerationInput, ImageGenerationOutput]):
    name = "offline_image"
    description = "Offline contract check"
    implemented = True
    input_schema = ImageGenerationInput
    output_schema = ImageGenerationOutput

    async def execute(self, inputs, *, api_key=None):
        assert api_key.get_secret_value() == "test-secret"
        return SkillResult[ImageGenerationOutput](
            status="success",
            data=ImageGenerationOutput(images=[GeneratedImage(media=IMAGE)], source="text-to-image"),
        )


async def test_registry_and_execution() -> None:
    registry = create_registry()
    metadata = registry.list_metadata(implemented_only=False)
    assert [item.name for item in metadata] == [
        "script_breakdown", "image_generation", "video_generation", "voice_design", "storyboard_composer",
    ]
    assert registry.list_metadata() == []
    for item in metadata:
        assert not item.implemented
        assert "apiKey" not in str(item.model_dump())
        assert "properties" in item.input_schema and "$defs" in item.output_schema
    try:
        registry.get("image_generation")
    except ValueError:
        pass
    else:
        raise AssertionError("pending skill published as callable")
    pending = registry.get("image_generation", implemented_only=False)
    result = await pending.run({"model": MODEL, "prompt": "frame"})
    assert result.error.code == "NOT_IMPLEMENTED" and result.data is None
    try:
        registry.register(pending)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate registration accepted")
    try:
        registry.get("missing")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown skill accepted")

    skill = OfflineImageSkill()
    ready = SkillRegistry()
    ready.register(skill)
    assert ready.get(skill.name) is skill and len(ready.list_metadata()) == 1
    result = await skill.run({"model": MODEL, "prompt": "frame"}, api_key=SecretStr("test-secret"))
    assert result.status == "success" and result.data.images[0].media.data == IMAGE["data"]
    assert "test-secret" not in result.model_dump_json()
    # Revalidation catches a model instance built without validation, not just dictionaries.
    invalid = ImageGenerationInput.model_construct(model=MODEL, prompt="")
    result = await skill.run(invalid, api_key=SecretStr("test-secret"))
    assert result.error.code == "INVALID_INPUT"

    class FailureSkill(OfflineImageSkill):
        async def execute(self, inputs, *, api_key=None):
            raise SkillExecutionError("PROVIDER_TIMEOUT", "Provider timed out", retryable=True)
    failed = await FailureSkill().run({"model": MODEL, "prompt": "frame"})
    assert failed.error.code == "PROVIDER_TIMEOUT" and failed.error.retryable

    class CancelledSkill(OfflineImageSkill):
        async def execute(self, inputs, *, api_key=None):
            raise asyncio.CancelledError()
    try:
        await CancelledSkill().run({"model": MODEL, "prompt": "frame"})
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancellation swallowed")

    class BrokenOutputSkill(OfflineImageSkill):
        async def execute(self, inputs, *, api_key=None):
            return SkillResult[VideoGenerationOutput](status="success", data=VideoGenerationOutput(video=VIDEO))
    try:
        await BrokenOutputSkill().run({"model": MODEL, "prompt": "frame"})
    except ValidationError:
        pass
    else:
        raise AssertionError("output schema violation swallowed")


async def test_opt_in_adapters() -> None:
    examples = {
        "script_breakdown": {"model": MODEL, "script": "An actor enters."},
        "image_generation": {"model": MODEL, "prompt": "frame", "aspect_ratio": "9:16"},
        "video_generation": {"model": MODEL, "prompt": "frame", "duration_ms": 4000},
        "voice_design": {"model": MODEL, "description": "Calm voice", "preview_text": "Hello"},
        "storyboard_composer": {"title": "episode", "shots": [{"key": "shot", "visual": IMAGE, "duration_ms": 4000}]},
    }
    for name, payload in examples.items():
        received = []

        async def host_run(inputs):
            received.append(inputs)
            return "host stored artifact"

        adapter = importlib.import_module(f"app.skills.{name}.adapter")
        tool = adapter.to_tool(host_run)
        assert tool.name == name and "apiKey" not in str(tool.args)
        assert await tool.ainvoke(payload) == "host stored artifact"
        assert len(received) == 1
        camel_payload = received[0].model_dump(mode="json", by_alias=True)
        assert await tool.ainvoke(camel_payload) == "host stored artifact"
        assert received[1] == received[0]
        assert set(tool.args) == set(camel_payload)


if __name__ == "__main__":
    test_core_import_isolation()
    test_contracts()
    asyncio.run(test_registry_and_execution())
    asyncio.run(test_opt_in_adapters())
    print("skills foundation checks passed")
