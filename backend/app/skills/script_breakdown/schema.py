"""One episode's script and production bible, using document-local keys."""

from typing import Literal, Self

from pydantic import Field, model_validator

from ..base import ModelSettings, NonEmptyStr, PositiveInt, SkillModel


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
    existing_shots: list[ShotSpec] = Field(default_factory=list)


class ScriptBreakdownOutput(SkillModel):
    characters: list[CharacterSpec]
    scenes: list[SceneSpec]
    props: list[PropSpec]
    shots: list[ShotSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent_keys(self) -> Self:
        for rows in (self.characters, self.scenes, self.props, self.shots):
            if len({row.key for row in rows}) != len(rows):
                raise ValueError("document keys must be unique within each collection")
        scenes = {row.key for row in self.scenes}
        characters = {row.key for row in self.characters}
        props = {row.key for row in self.props}
        for shot in self.shots:
            if shot.scene_key not in scenes:
                raise ValueError("shot refers to an unknown scene")
            if not set(shot.character_keys) <= characters or not set(shot.prop_keys) <= props:
                raise ValueError("shot refers to an unknown character or prop")
        return self
