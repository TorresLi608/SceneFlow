"""One episode's script and production bible, using document-local keys."""

from typing import Literal, Self

from pydantic import Field, model_validator

from ..base import Milliseconds, ModelSettings, NonEmptyStr, PositiveInt, SkillModel, require_unique


class CharacterSpec(SkillModel):
    key: NonEmptyStr
    name: NonEmptyStr
    description: str = ""
    visual_prompt: str = ""


class SceneSpec(SkillModel):
    key: NonEmptyStr
    name: NonEmptyStr
    description: str = ""


class PropSpec(SkillModel):
    key: NonEmptyStr
    name: NonEmptyStr
    description: str = ""
    visual_prompt: str = ""


class ShotSpec(SkillModel):
    key: NonEmptyStr
    scene_key: NonEmptyStr
    character_keys: list[NonEmptyStr] = Field(default_factory=list)
    prop_keys: list[NonEmptyStr] = Field(default_factory=list)
    narration: str = ""
    dialogue: str = ""
    visual_prompt: NonEmptyStr
    video_prompt: str = ""
    camera_move: str = ""
    transition: str = "cut"
    duration_ms: PositiveInt

    @model_validator(mode="after")
    def distinct_references(self) -> Self:
        require_unique(self.character_keys, "shot character keys")
        require_unique(self.prop_keys, "shot prop keys")
        return self


class ExistingShotSpec(SkillModel):
    """A shot the caller already has, as input to a re-breakdown or a motion pass.

    Looser than `ShotSpec`, which describes finished output: a host's stored shot may have
    no frame prompt yet, an undecided (zero) duration, and no scene assignment. Rejecting
    those would fail the whole breakdown over one blank row.
    """

    key: NonEmptyStr
    scene_key: str = ""
    character_keys: list[NonEmptyStr] = Field(default_factory=list)
    prop_keys: list[NonEmptyStr] = Field(default_factory=list)
    narration: str = ""
    dialogue: str = ""
    visual_prompt: str = ""
    video_prompt: str = ""
    camera_move: str = ""
    transition: str = ""
    duration_ms: Milliseconds = 0

    @model_validator(mode="after")
    def distinct_references(self) -> Self:
        require_unique(self.character_keys, "shot character keys")
        require_unique(self.prop_keys, "shot prop keys")
        return self


def _require_consistent_keys(characters, scenes, props, shots, *, scene_optional: bool) -> None:
    for rows, label in ((characters, "character"), (scenes, "scene"), (props, "prop"), (shots, "shot")):
        require_unique([row.key for row in rows], f"{label} keys")
    scene_keys = {row.key for row in scenes}
    character_keys = {row.key for row in characters}
    prop_keys = {row.key for row in props}
    for shot in shots:
        if not (scene_optional and not shot.scene_key) and shot.scene_key not in scene_keys:
            raise ValueError("shot refers to an unknown scene")
        if not set(shot.character_keys) <= character_keys or not set(shot.prop_keys) <= prop_keys:
            raise ValueError("shot refers to an unknown character or prop")


class ScriptBreakdownInput(SkillModel):
    model: ModelSettings
    script: NonEmptyStr
    language: NonEmptyStr = "zh"
    style: str = ""
    target: Literal["image", "video"] = "image"
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    characters: list[CharacterSpec] = Field(default_factory=list)
    scenes: list[SceneSpec] = Field(default_factory=list)
    props: list[PropSpec] = Field(default_factory=list)
    existing_shots: list[ExistingShotSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_document(self) -> Self:
        _require_consistent_keys(
            self.characters, self.scenes, self.props, self.existing_shots, scene_optional=True,
        )
        if self.target == "video" and not self.existing_shots:
            # The motion pass annotates shots in place; with none there is nothing to annotate.
            raise ValueError("video target requires existing shots")
        return self


class ScriptBreakdownOutput(SkillModel):
    characters: list[CharacterSpec]
    scenes: list[SceneSpec]
    props: list[PropSpec]
    shots: list[ShotSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent_keys(self) -> Self:
        _require_consistent_keys(self.characters, self.scenes, self.props, self.shots, scene_optional=False)
        return self
