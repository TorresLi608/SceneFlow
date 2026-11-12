"""Standalone core: only Pydantic is needed for contracts and discovery."""

from .base import BaseSkill, MediaArtifact, ModelSettings, SkillExecutionError, SkillResult
from .registry import SkillRegistry, create_registry

__all__ = [
    "BaseSkill", "MediaArtifact", "ModelSettings", "SkillExecutionError", "SkillResult",
    "SkillRegistry", "create_registry",
]
