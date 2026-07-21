from __future__ import annotations

import tempfile
from pathlib import Path

import database
from database import init_db
from routers.admin import create_redemption_code, create_user, list_redemption_codes
from routers.users import redeem_code


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
