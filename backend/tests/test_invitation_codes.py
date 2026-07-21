from __future__ import annotations

import tempfile
from pathlib import Path

from app.api.v1.admin import create_invitation_code, list_invitation_codes
from app.api.v1.auth import register
from app.core import database
from app.core.database import init_db


def test_invitation_code_is_required_and_consumed() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test.db"
        try:
            init_db()
            invitation = create_invitation_code({"days": 7}, 1)["invitationCode"]

            try:
                register({"username": "alice", "password": "password"})
                raise AssertionError("registration without an invitation code should fail")
            except Exception as exc:
                assert getattr(exc, "detail", None) == "invitation code required"

            register({"username": "alice", "password": "password", "invitationCode": invitation["code"]})
            result = list_invitation_codes(1, status="used", search="ali", page=1, page_size=10)
            listed = result["invitationCodes"]

            assert listed[0]["status"] == "used"
            assert listed[0]["usedBy"]["username"] == "alice"
            assert listed[0]["usedAt"] is not None
            assert listed[0]["createdBy"]["username"] == "superAdmin"
            assert result["pagination"]["total"] == 1
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_invitation_code_is_required_and_consumed()
