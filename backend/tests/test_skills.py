"""Offline checks for the pure skill boundary; no application/provider imports."""

from __future__ import annotations

import asyncio
import copy
import importlib
import pickle
import subprocess
import sys
from decimal import Decimal

from pydantic import SecretStr, ValidationError

from app.skills import (
    BaseSkill, MediaArtifact, ModelSettings, SkillExecutionError, SkillResult, SkillUnavailableError,
    SkillUsage, create_registry,
)
from app.skills.image_generation import ImageGenerationInput, ImageGenerationOutput
from app.skills.image_generation.schema import GeneratedImage
from app.skills.registry import SkillRegistry
from app.skills.script_breakdown import ScriptBreakdownInput, ScriptBreakdownOutput
from app.skills.storyboard_composer import StoryboardComposerInput, StoryboardComposerOutput
from app.skills.video_generation import VideoGenerationInput, VideoGenerationOutput
from app.skills.voice_design import VoiceDesignInput, VoiceDesignOutput


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
        if fullname.split(".")[0] in roots or (fullname.startswith("app.") and not fullname.startswith("app.skills")):
            raise AssertionError("forbidden core dependency: " + fullname)
sys.meta_path.insert(0, Guard())
from app.skills import create_registry
import app.skills.tool_adapter
for name in ("script_breakdown", "image_generation", "video_generation", "voice_design", "storyboard_composer"):
    __import__("app.skills." + name + ".adapter")
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
    rejected(ModelSettings, {"provider": "test", "model": "offline", "baseUrl": "https://user:key@example.com/v1"})
    assert str(ModelSettings(provider="test", model="offline", base_url="https://example.com/v1").base_url)
    rejected(VideoGenerationInput, {"model": MODEL, "prompt": "frame", "durationMs": True})
    rejected(VideoGenerationInput, {"model": MODEL, "prompt": "frame", "durationMs": 4000, "lastFrame": AUDIO})
    video = VideoGenerationInput(model=MODEL, prompt="frame", duration_ms=4000, first_frame=IMAGE)
    assert video.fps is None and video.last_frame is None and video.reference_images == []
    # SceneFlow renders shots that pin only the closing frame, so the contract must too.
    tail_only = VideoGenerationInput(model=MODEL, prompt="frame", duration_ms=4000, last_frame=IMAGE)
    assert tail_only.first_frame is None and tail_only.last_frame is not None
    rejected(VoiceDesignInput, {"model": MODEL, "mode": "clone"})
    rejected(VoiceDesignInput, {"model": MODEL, "mode": "synthesize", "lines": [{"key": "line", "text": "hello"}]})
    voice = {"provider": "test", "voiceId": "v1", "targetModel": "offline"}
    design = {"model": MODEL, "description": "Calm voice", "previewText": "Hello"}
    rejected(VoiceDesignInput, {**design, "referenceAudio": AUDIO})
    rejected(VoiceDesignInput, {**design, "voice": voice})
    rejected(VoiceDesignOutput, {"clips": [{"lineKey": "a", "audio": AUDIO}, {"lineKey": "a", "audio": AUDIO}]})
    # A stored shot may be blank: no frame prompt, undecided duration, no scene assignment.
    blank = ScriptBreakdownInput.model_validate({
        "model": MODEL, "script": "An actor enters.", "target": "video",
        "existingShots": [{"key": "shot-1", "narration": "enters"}],
    })
    assert blank.existing_shots[0].duration_ms == 0 and blank.existing_shots[0].visual_prompt == ""
    rejected(ScriptBreakdownInput, {"model": MODEL, "script": "An actor enters.", "target": "video"})
    rejected(ScriptBreakdownInput, {
        "model": MODEL, "script": "s",
        "characters": [{"key": "c", "name": "A"}, {"key": "c", "name": "B"}],
    })
    rejected(ScriptBreakdownInput, {
        "model": MODEL, "script": "s", "existingShots": [{"key": "shot-1", "characterKeys": ["ghost"]}],
    })
    rejected(ScriptBreakdownOutput, {
        "characters": [{"key": "c", "name": "A"}], "scenes": [{"key": "s", "name": "S"}], "props": [],
        "shots": [{"key": "shot", "sceneKey": "s", "characterKeys": ["c", "c"], "visualPrompt": "frame", "durationMs": 4000}],
    })
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
    # An animated image loops for the shot; only video can run out of source footage.
    gif = {"mediaType": "image/gif", "data": b"gif", "durationMs": 1000}
    assert StoryboardComposerInput.model_validate({"title": "episode", "shots": [{**shot, "visual": gif}]})
    rejected(StoryboardComposerInput, {
        "title": "episode", "shots": [{**shot, "visual": {**VIDEO, "durationMs": 1000}}],
    })
    rejected(StoryboardComposerInput, {
        "title": "episode",
        "shots": [{**shot, "audio": [{"media": {**AUDIO, "durationMs": 500}, "durationMs": 4000}]}],
    })
    rejected(SkillResult[ImageGenerationOutput], {"status": "success"})
    rejected(SkillResult[ImageGenerationOutput], {"status": "error"})
    usage = SkillUsage(provider="test", model="offline", quantity=Decimal("0.125"), unit="second")
    assert '"quantity":"0.125"' in usage.model_dump_json()
    assert usage.input_tokens is None
    rejected(SkillUsage, {"provider": "test", "model": "offline", "quantity": "1"})
    rejected(SkillUsage, {"provider": "test", "model": "offline", "unit": "image"})
    # A bare result cannot carry output; the failure has to say so, not blame every field.
    output = ImageGenerationOutput(images=[GeneratedImage(media=IMAGE)], source="text-to-image")
    try:
        SkillResult(status="success", data=output)
    except ValidationError as exc:
        assert "SkillResult[Output]" in str(exc)
    else:
        raise AssertionError("bare result accepted output data")
    error = SkillExecutionError("PROVIDER_TIMEOUT", "Provider timed out", retryable=True)
    for clone in (pickle.loads(pickle.dumps(error)), copy.copy(error)):
        assert clone.error == error.error and str(clone) == "Provider timed out"
    assert SkillExecutionError("", " ").error.code == "SKILL_FAILED"


class OfflineImageSkill(BaseSkill[ImageGenerationInput, ImageGenerationOutput]):
    name = "offline_image"
    description = "Offline contract check"
    implemented = True
    input_schema = ImageGenerationInput
    output_schema = ImageGenerationOutput

    async def execute(self, inputs, *, api_key=None):
        assert api_key.get_secret_value() == "test-secret"
        return self.success(
            ImageGenerationOutput(images=[GeneratedImage(media=IMAGE)], source="text-to-image"),
            usage=[SkillUsage(provider="test", model="offline", quantity=Decimal("1"), unit="image")],
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
        # Published as callers receive it: a Decimal quantity is a string, never a number.
        quantity = item.output_schema["$defs"]["SkillUsage"]["properties"]["quantity"]
        assert {"type": "number"} not in [{"type": option.get("type")} for option in quantity["anyOf"]]
    try:
        registry.get("image_generation")
    except SkillUnavailableError:
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
    except SkillUnavailableError:
        pass
    else:
        raise AssertionError("unknown skill accepted")

    class OddlyNamedSkill(OfflineImageSkill):
        name = "bad name!"
    try:
        SkillRegistry().register(OddlyNamedSkill())
    except ValidationError:
        pass
    else:
        raise AssertionError("a name no tool API accepts was registered")

    class UndeclaredSkill(BaseSkill):
        name = "undeclared"
        description = "No schemas"

        async def execute(self, inputs, *, api_key=None):
            raise AssertionError("never runs")
    try:
        SkillRegistry().register(UndeclaredSkill())
    except TypeError as exc:
        assert "input_schema" in str(exc)
    else:
        raise AssertionError("a skill without schemas was registered")

    skill = OfflineImageSkill()
    ready = SkillRegistry()
    ready.register(skill)
    assert ready.get(skill.name) is skill and len(ready.list_metadata()) == 1
    result = await skill.run({"model": MODEL, "prompt": "frame"}, api_key=SecretStr("test-secret"))
    assert result.status == "success" and result.data.images[0].media.data == IMAGE["data"]
    assert result.usage[0].unit == "image" and "test-secret" not in result.model_dump_json()
    # Revalidation catches a model instance built without validation, not just dictionaries.
    invalid = ImageGenerationInput.model_construct(model=MODEL, prompt="")
    result = await skill.run(invalid, api_key=SecretStr("test-secret"))
    assert result.error.code == "INVALID_INPUT"
    # The caller learns which fields failed and why, and none of what it sent.
    result = await skill.run({"model": MODEL, "prompt": "PRIVATE SCRIPT", "aspectRatio": "PRIVATE RATIO"})
    assert result.error.code == "INVALID_INPUT"
    assert result.error.details == ["aspectRatio: string_pattern_mismatch"]
    assert "PRIVATE" not in result.model_dump_json()
    # Cross-field rules only run once every field is individually valid.
    result = await skill.run({"model": MODEL, "prompt": "PRIVATE SCRIPT", "width": 5})
    assert result.error.details == ["(input): width and height must be supplied together"]
    assert "PRIVATE" not in result.model_dump_json()

    class PartialFailureSkill(OfflineImageSkill):
        async def execute(self, inputs, *, api_key=None):
            return self.failure(
                "PROVIDER_PARTIAL", "One image failed", retryable=True,
                data=ImageGenerationOutput(images=[GeneratedImage(media=IMAGE)], source="text-to-image"),
            )
    partial = await PartialFailureSkill().run({"model": MODEL, "prompt": "frame"})
    assert partial.status == "error" and partial.error.retryable and len(partial.data.images) == 1

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
    # What an agent supplies. Provider, model and base URL are the host's to decide.
    examples = {
        "script_breakdown": {"script": "An actor enters."},
        "image_generation": {"prompt": "frame", "aspect_ratio": "9:16"},
        "video_generation": {"prompt": "frame", "duration_ms": 4000},
        "voice_design": {"description": "Calm voice", "preview_text": "Hello"},
        "storyboard_composer": {"title": "episode", "shots": [{"key": "shot", "visual": IMAGE, "duration_ms": 4000}]},
    }
    for name, payload in examples.items():
        received = []

        async def host_run(inputs):
            received.append(inputs)
            return "host stored artifact"

        adapter = importlib.import_module(f"app.skills.{name}.adapter")
        takes_model = name != "storyboard_composer"
        tool = adapter.to_tool(host_run, **({"model": MODEL} if takes_model else {}))
        assert tool.name == name and "apiKey" not in str(tool.args)
        assert "model" not in tool.args and "ModelSettings" not in str(tool.tool_call_schema)
        assert await tool.ainvoke(payload) == "host stored artifact"
        assert len(received) == 1
        if takes_model:
            assert received[0].model.provider == "test" and received[0].model.model == "offline"
        camel_payload = received[0].model_dump(mode="json", by_alias=True)
        camel_payload.pop("model", None)
        assert await tool.ainvoke(camel_payload) == "host stored artifact"
        assert received[1] == received[0]
        assert set(tool.args) == set(camel_payload)
        if takes_model:
            # An agent cannot redirect the call to its own provider or endpoint.
            refused = await tool.ainvoke({**payload, "model": {"provider": "evil", "model": "x", "baseUrl": "http://169.254.169.254"}})
            assert "set by the host" in refused and len(received) == 2
            try:
                adapter.to_tool(host_run)
            except (TypeError, ValueError):
                pass
            else:
                raise AssertionError("a model-taking skill was bound without host model settings")

    received = []

    async def image_run(inputs):
        received.append(inputs)
        return "host stored artifact"

    image_adapter = importlib.import_module("app.skills.image_generation.adapter")
    tool = image_adapter.to_tool(image_run, model=MODEL)
    # Bad arguments return a sanitized tool message the agent can act on.
    message = await tool.ainvoke({"prompt": "PRIVATE SCRIPT", "aspectRatio": "PRIVATE RATIO"})
    assert "aspectRatio: string_pattern_mismatch" in message and "PRIVATE" not in message and not received
    # Host-resolved references are bound, hidden from the agent, and cannot be overridden.
    tool = image_adapter.to_tool(image_run, model=MODEL, host_inputs={"references": [IMAGE]})
    assert "references" not in tool.args and "MediaArtifact" not in str(tool.tool_call_schema)
    assert await tool.ainvoke({"prompt": "frame"}) == "host stored artifact"
    assert received[0].references[0].data == IMAGE["data"]
    assert "set by the host" in await tool.ainvoke({"prompt": "frame", "references": []})
    try:
        image_adapter.to_tool(image_run, model=MODEL, host_inputs={"userId": 1})
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown host input was bound")


if __name__ == "__main__":
    test_core_import_isolation()
    test_contracts()
    asyncio.run(test_registry_and_execution())
    asyncio.run(test_opt_in_adapters())
    print("skills foundation checks passed")
