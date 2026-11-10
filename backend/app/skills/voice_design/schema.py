"""Design/clone/select a provider voice or synthesize an ordered dialogue batch."""

from typing import Literal, Self

from pydantic import Field, model_validator

from ..base import MediaArtifact, ModelSettings, NonEmptyStr, SkillModel, require_media_kind


class VoiceSpec(SkillModel):
    provider: NonEmptyStr
    voice_id: NonEmptyStr
    target_model: NonEmptyStr


class DialogueLine(SkillModel):
    key: NonEmptyStr
    text: NonEmptyStr
    voice: VoiceSpec | None = None


class VoiceDesignInput(SkillModel):
    model: ModelSettings
    mode: Literal["design", "clone", "select", "synthesize"] = "design"
    language: NonEmptyStr = "zh"
    description: str = ""
    preview_text: str = ""
    preferred_name: NonEmptyStr = "voice"
    reference_audio: MediaArtifact | None = None
    voice: VoiceSpec | None = None
    lines: list[DialogueLine] = Field(default_factory=list)
    output_format: Literal["wav", "mp3", "pcm"] = "wav"

    @model_validator(mode="after")
    def valid_mode(self) -> Self:
        require_media_kind(self.reference_audio, "audio")
        if self.mode == "design" and (not self.description or not self.preview_text):
            raise ValueError("voice design requires description and preview text")
        if self.mode == "clone" and self.reference_audio is None:
            raise ValueError("voice clone requires reference audio")
        if self.mode == "select" and self.voice is None:
            raise ValueError("voice selection requires a provider voice")
        if self.mode == "synthesize":
            if not self.lines or any(line.voice is None and self.voice is None for line in self.lines):
                raise ValueError("synthesis requires lines and a voice for every line")
        elif self.lines:
            raise ValueError("dialogue lines require synthesize mode")
        if len({line.key for line in self.lines}) != len(self.lines):
            raise ValueError("dialogue line keys must be unique")
        return self


class DialogueAudio(SkillModel):
    line_key: NonEmptyStr
    audio: MediaArtifact

    @model_validator(mode="after")
    def audio_media(self) -> Self:
        require_media_kind(self.audio, "audio")
        return self


class VoiceDesignOutput(SkillModel):
    voice: VoiceSpec | None = None
    preview_audio: MediaArtifact | None = None
    clips: list[DialogueAudio] = Field(default_factory=list)

    @model_validator(mode="after")
    def audio_output(self) -> Self:
        require_media_kind(self.preview_audio, "audio")
        if self.voice is None and not self.clips:
            raise ValueError("voice output requires a voice or dialogue audio clips")
        return self
