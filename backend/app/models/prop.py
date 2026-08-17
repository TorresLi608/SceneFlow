"""Props: the objects a series has to draw the same way every time it shows them.

The same problem as `Character`, one level down. A locket that changes shape between shots
breaks continuity as visibly as a face does, and the fix is the same — a named reference
image, tiled with its siblings into one sheet the renderer carries.
"""

from __future__ import annotations

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class Prop(SQLModel, table=True):
    __tablename__ = "props"
    __table_args__ = (
        Index("idx_props_project_id", "project_id"),
        Index("idx_props_deleted_at", "deleted_at"),
    )

    id: str = Field(primary_key=True)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
    project_id: str = Field(foreign_key="projects.id", ondelete="CASCADE")
    name: str
    description: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # Overrides the built-in prop instructions in `prompt_service` when non-empty.
    system_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # The drafted prompt after the user reviewed and possibly edited it; this is what draws
    # the image, so the preview step is not merely advisory.
    final_prompt: str = Field(default="", sa_column_kwargs={"server_default": text("''")})
    # A path relative to PRIVATE_GENERATED_DIR, never a URL — signed links expire.
    image_path: str | None = None
    order_num: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
