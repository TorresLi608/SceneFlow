"""The series bible: who appears in the show and what keeps them recognisable across episodes."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel


class Character(SQLModel, table=True):
    """A recurring cast member, pinned to one look, one image model, and one voice.

    Consistency across episodes comes from three things held here: the reference sheet
    (passed to image-to-image so the face carries over), `appearance_prompt` (injected
    verbatim into every prompt the character appears in), and the frozen model/voice
    columns (so changing the account's default model later cannot restyle an established
    character mid-series). Alternate looks go in `CharacterState`.
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
    # Legacy: the single card portrait from before looks were split into states. Nothing
    # writes it any more, but existing series still render against it, so resolution falls
    # back to it when a character has no state image.
    reference_image_path: str | None = None
    # Every state of this character tiled into one sheet, so a render can carry the whole
    # cast as a couple of references instead of blowing past the provider's reference cap.
    sheet_image_path: str | None = None
    # The exact configuration that produced the reference portrait.
    image_provider: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    image_model: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    image_base_url: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    voice_provider: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    voice_model: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # The voice profile bound to this character, if any. The profile is the source of truth
    # once set; the two columns above stay as the fallback for cards bound to nothing.
    #
    # Deliberately not a foreign key: SQLite cannot add a constrained column in place, and a
    # batch recreate of this table reflects into the shared SQLModel metadata and reorders
    # columns unpredictably. `voice_service.delete_voice_profile` clears the binding instead,
    # which is what ON DELETE SET NULL would have done.
    voice_profile_id: str | None = None
    # Set once the user approves the portrait. Locked cards are never regenerated in bulk.
    is_locked: bool = Field(default=False, sa_column_kwargs={"server_default": text("0")})
    order_num: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})


class CharacterState(SQLModel, table=True):
    """One look a character can appear in: an age, an outfit, a transformation.

    States are parallel forms of the same person — 青年 / 幼年 / 老年, or two sets of
    clothes — not a timeline. The episode range is an optional narrowing for the case where
    a look genuinely only applies from some episode onward; a state that leaves it unset is
    simply always available. (It was the other way round when this table was
    `character_variants`, and episode-scoped variants are still resolved from these rows.)

    `reference_image_path` holds the state's turnaround sheet — front, three-quarter, and
    profile in one image — which is what actually holds a face steady at render time.
    """

    __tablename__ = "character_states"
    __table_args__ = (
        CheckConstraint("from_episode IS NULL OR from_episode > 0"),
        CheckConstraint("to_episode IS NULL OR from_episode IS NULL OR to_episode >= from_episode"),
        Index("idx_character_states_character", "character_id", "from_episode"),
        Index("idx_character_states_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    character_id: str = Field(foreign_key="characters.id", ondelete="CASCADE")
    name: str
    # A short note on what this state is ("十六岁，校服"), fed to the model that drafts
    # `final_prompt`. Distinct from `appearance_prompt`, which is what reaches the renderer.
    description: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    appearance_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # Overrides the built-in turnaround instructions in `prompt_service` when non-empty.
    system_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # The drafted prompt after the user has reviewed and possibly edited it. This, not the
    # template, is what draws the sheet — the whole point of the preview step.
    final_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    reference_image_path: str | None = None
    voice_model: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    order_num: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    # NULL means the state is not pinned to any episode range and is always available.
    from_episode: int | None = None
    to_episode: int | None = None


class SceneCharacter(SQLModel, table=True):
    """Which cast members appear in a shot; drives prompt assembly and reference images."""

    __tablename__ = "scene_characters"
    __table_args__ = (Index("idx_scene_characters_character", "character_id"),)

    scene_id: str = Field(primary_key=True, foreign_key="scenes.id", ondelete="CASCADE")
    character_id: str = Field(primary_key=True, foreign_key="characters.id", ondelete="CASCADE")
    created_at: str | None = None
