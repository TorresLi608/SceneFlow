"""store optional video first/last frame references"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("video_first_frame_json", sa.Text(), nullable=False, server_default=""))
    op.add_column("scenes", sa.Column("video_last_frame_json", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("scenes") as batch:
        batch.drop_column("video_last_frame_json")
        batch.drop_column("video_first_frame_json")
