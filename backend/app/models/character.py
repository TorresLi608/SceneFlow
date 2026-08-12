"""The series bible: who appears in the show and what keeps them recognisable across episodes."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel


class Character(SQLModel, table=True):
    """A recurring cast member, pinned to one look, one image model, and one voice.

    Consistency across episodes comes from three things held here: the reference portrait
    (passed to image-to-image so the face carries over), `appearance_prompt` (injected
    verbatim into every prompt the character appears in), and the frozen model/voice
    columns (so changing the account's default model later cannot restyle an established
    character mid-series). Deliberate changes go in `CharacterVariant`.
    """

    __tablename__ = "characters"
    __table_args__ = (
        Index("idx_characters_project_id", "project_id"),
        Index("idx_characters_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    name: str
    # Comma-separated names the script also uses for this character, so extraction can
    # match "小满" and "林小满" to one card instead of creating two.
    aliases: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    description: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    appearance_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    reference_image_path: str | None = None
    # The exact configuration that produced the reference portrait.
    image_provider: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    image_model: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    image_base_url: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    voice_provider: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    voice_model: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # Set once the user approves the portrait. Locked cards are never regenerated in bulk.
    is_locked: bool = Field(default=False, sa_column_kwargs={"server_default": text("0")})
    order_num: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})


class CharacterVariant(SQLModel, table=True):
    """A deliberate change of look or voice over a range of episodes.

    Characters stay identical by default; a variant is how a series says "this one grew up
    in episode 5". Resolution picks the variant whose episode range covers the episode being
    generated, and falls back to the character card when none does.
    """

    __tablename__ = "character_variants"
    __table_args__ = (
        CheckConstraint("from_episode > 0"),
        CheckConstraint("to_episode IS NULL OR to_episode >= from_episode"),
        Index("idx_character_variants_character", "character_id", "from_episode"),
        Index("idx_character_variants_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    character_id: str = Field(foreign_key="characters.id", ondelete="CASCADE")
    name: str
    appearance_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    reference_image_path: str | None = None
    voice_model: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    from_episode: int = Field(default=1, sa_column_kwargs={"server_default": text("1")})
    # NULL means the variant stays in effect for every later episode.
    to_episode: int | None = None


class SceneCharacter(SQLModel, table=True):
    """Which cast members appear in a shot; drives prompt assembly and reference images."""

    __tablename__ = "scene_characters"
    __table_args__ = (Index("idx_scene_characters_character", "character_id"),)

    scene_id: str = Field(primary_key=True, foreign_key="scenes.id", ondelete="CASCADE")
    character_id: str = Field(primary_key=True, foreign_key="characters.id", ondelete="CASCADE")
    created_at: str | None = None
