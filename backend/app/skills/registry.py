"""Explicit registration: no filesystem scanning, environment reads, or DB imports."""

from typing import Any

from .base import BaseSkill, SkillMetadata


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill[Any, Any]] = {}

    def register(self, skill: BaseSkill[Any, Any]) -> None:
        skill.metadata()  # Validate metadata/schema before publishing the entry.
        if skill.name in self._skills:
            raise ValueError(f"skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str, *, implemented_only: bool = True) -> BaseSkill[Any, Any]:
        skill = self._skills[name]
        if implemented_only and not skill.implemented:
            raise ValueError(f"skill is not implemented: {name}")
        return skill

    def list_metadata(self, *, implemented_only: bool = True) -> list[SkillMetadata]:
        return [
            skill.metadata() for skill in self._skills.values()
            if not implemented_only or skill.implemented
        ]


def create_registry() -> SkillRegistry:
    # Local imports keep schema-only consumers independent of skill implementations.
    from .image_generation import ImageGenerationSkill
    from .script_breakdown import ScriptBreakdownSkill
    from .storyboard_composer import StoryboardComposerSkill
    from .video_generation import VideoGenerationSkill
    from .voice_design import VoiceDesignSkill

    registry = SkillRegistry()
    for skill_type in (
        ScriptBreakdownSkill, ImageGenerationSkill, VideoGenerationSkill,
        VoiceDesignSkill, StoryboardComposerSkill,
    ):
        registry.register(skill_type())
    return registry

