"""add video model capabilities

Revision ID: 7c1a9f4e2b6d
Revises: 2df5b20c732e
Create Date: 2026-08-13
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel


revision: str = "7c1a9f4e2b6d"
down_revision: Union[str, Sequence[str], None] = "2df5b20c732e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("model_configs")}
    if "video_capabilities_json" not in columns:
        with op.batch_alter_table("model_configs") as batch_op:
            batch_op.add_column(sa.Column("video_capabilities_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True))

    standard = json.dumps({
        "qualities": [], "fps": [24],
        "resolutions": ["1280x720", "720x1280", "1024x1024", "1920x1080"],
        "promptExtend": False, "minDuration": 3, "maxDuration": 15,
        "referenceImagesRequired": False, "maxReferenceImages": 1,
        "referenceVideo": False, "drivingAudio": False,
    }, separators=(",", ":"))
    gemini = json.dumps({
        "qualities": [], "fps": [24],
        "resolutions": ["1280x720", "720x1280", "1920x1080"],
        "promptExtend": False, "minDuration": 3, "maxDuration": 15,
        "referenceImagesRequired": False, "maxReferenceImages": 1,
        "referenceVideo": False, "drivingAudio": False,
    }, separators=(",", ":"))
    connection = op.get_bind()
    for config_id, model_name in connection.execute(sa.text("SELECT id, model_name FROM model_configs WHERE purpose='video' AND provider='qwen'")):
        model = (model_name or "").lower()
        is_i2v = "-i2v" in model
        is_r2v = "-r2v" in model
        is_video_edit = "videoedit" in model
        qwen = json.dumps({
            "qualities": ["480p", "720p", "1080p"], "fps": [], "resolutions": [],
            "promptExtend": is_i2v, "minDuration": 2 if is_i2v else 3, "maxDuration": 15,
            "referenceImagesRequired": is_i2v or is_r2v,
            "maxReferenceImages": 5 if is_r2v else (1 if is_i2v or is_video_edit else 0),
            "referenceVideo": is_video_edit, "drivingAudio": is_i2v,
        }, separators=(",", ":"))
        connection.execute(sa.text("UPDATE model_configs SET video_capabilities_json=:value WHERE id=:id"), {"id": config_id, "value": qwen})
    connection.execute(sa.text("UPDATE model_configs SET video_capabilities_json=:value WHERE purpose='video' AND provider='gemini'"), {"value": gemini})
    connection.execute(sa.text("UPDATE model_configs SET video_capabilities_json=:value WHERE purpose='video' AND provider NOT IN ('qwen', 'gemini')"), {"value": standard})


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("model_configs")}
    if "video_capabilities_json" in columns:
        with op.batch_alter_table("model_configs") as batch_op:
            batch_op.drop_column("video_capabilities_json")
