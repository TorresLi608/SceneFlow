from __future__ import annotations

import tempfile
from pathlib import Path

import database
from database import init_db
from routers.admin import create_invitation_code, list_invitation_codes
from routers.auth import register


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
            listed = list_invitation_codes(1)["invitationCodes"]

            assert listed[0]["status"] == "used"
            assert listed[0]["usedBy"]["username"] == "alice"
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_invitation_code_is_required_and_consumed()
