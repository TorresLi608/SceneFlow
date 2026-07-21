from __future__ import annotations

import tempfile
from pathlib import Path

from app.api.v1.admin import create_redemption_code, create_user, list_redemption_codes
from app.api.v1.users import redeem_code
from app.core import database
from app.core.database import init_db


def test_redemption_code_credits_balance_once() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test.db"
        try:
            init_db()
            user = create_user({"username": "alice", "password": "password"}, 1)["user"]
            redemption = create_redemption_code({"amount": "12.50", "days": 7}, 1)["redemptionCode"]

            result = redeem_code({"code": redemption["code"]}, user["id"])
            assert result["amountMicros"] == 12_500_000
            assert result["user"]["balanceMicros"] == 12_500_000

            listed = list_redemption_codes(1, status="redeemed", page=1, page_size=10)
            assert listed["pagination"]["total"] == 1
            assert listed["redemptionCodes"][0]["redeemedBy"]["username"] == "alice"
            assert listed["redemptionCodes"][0]["redeemedAt"] is not None
            assert listed["redemptionCodes"][0]["createdBy"]["username"] == "superAdmin"

            try:
                redeem_code({"code": redemption["code"]}, user["id"])
                raise AssertionError("a redemption code must only be credited once")
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 409

            try:
                create_redemption_code({"amount": "NaN", "days": 7}, 1)
                raise AssertionError("non-finite amounts must be rejected")
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 400
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_redemption_code_credits_balance_once()
