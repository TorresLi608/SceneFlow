"""split the generation retention window into one per standalone menu

Revision ID: e4b7c2d9a1f5
Revises: d9e2f3a4b5c6
Create Date: 2026-09-20

`system_settings` is key/value, so no DDL: the single `generation_retention_days` row
becomes `generation_retention_image_days` and `generation_retention_video_days` so an
operator's existing policy keeps applying to the same two menus. Chat and voice have no
row, which the service reads as "keep forever", so the new menus start with no cleanup.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "e4b7c2d9a1f5"
down_revision: Union[str, Sequence[str], None] = "d9e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_KEY = "generation_retention_days"
SPLIT_KEYS = ("generation_retention_image_days", "generation_retention_video_days")


def upgrade() -> None:
    connection = op.get_bind()
    if "system_settings" not in set(inspect(connection).get_table_names()):
        return
    legacy = connection.execute(
        sa.text("SELECT value, updated_at, updated_by_user_id FROM system_settings WHERE key = :key"),
        {"key": LEGACY_KEY},
    ).fetchone()
    if legacy is not None:
        for key in SPLIT_KEYS:
            existing = connection.execute(sa.text("SELECT 1 FROM system_settings WHERE key = :key"), {"key": key}).fetchone()
            if existing is None:
                connection.execute(
                    sa.text("INSERT INTO system_settings (key, value, updated_at, updated_by_user_id) VALUES (:key, :value, :updated_at, :user_id)"),
                    {"key": key, "value": legacy[0], "updated_at": legacy[1], "user_id": legacy[2]},
                )
        connection.execute(sa.text("DELETE FROM system_settings WHERE key = :key"), {"key": LEGACY_KEY})


def downgrade() -> None:
    connection = op.get_bind()
    if "system_settings" not in set(inspect(connection).get_table_names()):
        return
    # The old code had one window for both menus; the image window is the closest single value.
    image = connection.execute(
        sa.text("SELECT value, updated_at, updated_by_user_id FROM system_settings WHERE key = :key"),
        {"key": SPLIT_KEYS[0]},
    ).fetchone()
    if image is not None:
        existing = connection.execute(sa.text("SELECT 1 FROM system_settings WHERE key = :key"), {"key": LEGACY_KEY}).fetchone()
        if existing is None:
            connection.execute(
                sa.text("INSERT INTO system_settings (key, value, updated_at, updated_by_user_id) VALUES (:key, :value, :updated_at, :user_id)"),
                {"key": LEGACY_KEY, "value": image[0], "updated_at": image[1], "user_id": image[2]},
            )
    connection.execute(
        sa.text("DELETE FROM system_settings WHERE key IN ('generation_retention_image_days', 'generation_retention_video_days', 'generation_retention_chat_days', 'generation_retention_voice_days')")
    )
