from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.admin import create_redemption_code, create_user, list_redemption_codes
from app.api.v1.users import redeem_code, router
from app.core import database
from app.core.database import db, init_db
from app.core.security import token_for
from app.models import RedemptionCode


def test_redemption_code_credits_balance_once() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "test.db"
        try:
            init_db()
            user = create_user({"username": "alice", "password": "password"}, 1)["user"]
            redemption = create_redemption_code({"amount": "12.500001", "days": 7}, 1)["redemptionCode"]

            result = redeem_code({"code": redemption["code"]}, user["id"])
            assert result["amountMicros"] == "12500001"
            assert result["user"]["balanceMicros"] == "12500001"

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


def test_personal_redemption_history_is_private_and_paginated() -> None:
    original_path = database.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        database.DB_PATH = Path(directory) / "history.db"
        try:
            init_db()
            alice = create_user({"username": "alice", "password": "password"}, 1)["user"]
            bob = create_user({"username": "bob", "password": "password"}, 1)["user"]
            headers = {"Authorization": f"Bearer {token_for(alice['id'])}"}
            app = FastAPI()
            app.include_router(router)
            path = "/api/users/redemptions"
            with TestClient(app) as client:
                assert client.get(path).status_code == 401
                empty = client.get(path, headers=headers)
                assert empty.status_code == 200, empty.text
                assert empty.json() == {
                    "redemptions": [],
                    "pagination": {"total": 0, "page": 1, "pageSize": 10, "pageCount": 1},
                }

                code = create_redemption_code({"amount": "12.500001", "days": 7}, 1)["redemptionCode"]
                redeemed = client.post("/api/users/redeem", json={"code": code["code"]}, headers=headers)
                assert redeemed.status_code == 200, redeemed.text
                history = client.get(path, headers=headers).json()
                assert history["pagination"]["total"] == 1
                item = history["redemptions"][0]
                assert item == {"id": code["id"], "code": code["code"], "amountMicros": "12500001", "redeemedAt": item["redeemedAt"]}
                assert item["redeemedAt"]

                # Old/expired codes stay in history; tied redemption times use descending IDs.
                with db() as session:
                    for name, owner, stamp, amount in (
                        ("RC-OLD-A", alice["id"], "2024-01-05T00:00:00+00:00", 1),
                        ("RC-OLD-B", alice["id"], "2024-01-05T00:00:00+00:00", 9007199254740993),
                        ("RC-OTHER-USER", bob["id"], item["redeemedAt"], 5000000),
                        ("RC-UNUSED", None, None, 1000000),
                    ):
                        session.add(RedemptionCode(
                            code=name, amount_micros=amount,
                            created_at="2024-01-01T00:00:00+00:00", expires_at="2024-02-01T00:00:00+00:00",
                            redeemed_by_user_id=owner, redeemed_at=stamp,
                        ))

                first = client.get(path, params={"pageSize": 2, "userId": bob["id"]}, headers=headers)
                assert first.status_code == 200, first.text
                assert first.json()["pagination"] == {"total": 3, "page": 1, "pageSize": 2, "pageCount": 2}
                assert [row["code"] for row in first.json()["redemptions"]] == [code["code"], "RC-OLD-B"]
                assert first.json()["redemptions"][1]["amountMicros"] == "9007199254740993"
                second = client.get(path, params={"page": 2, "pageSize": 2}, headers=headers).json()
                assert second["pagination"] == {"total": 3, "page": 2, "pageSize": 2, "pageCount": 2}
                assert [row["code"] for row in second["redemptions"]] == ["RC-OLD-A"]
                assert second["redemptions"][0]["amountMicros"] == "1"
                assert client.get(path, params={"page": 3, "pageSize": 2}, headers=headers).json()["redemptions"] == []

                bob_history = client.get(path, headers={"Authorization": f"Bearer {token_for(bob['id'])}"}).json()
                assert bob_history["pagination"]["total"] == 1
                assert [row["code"] for row in bob_history["redemptions"]] == ["RC-OTHER-USER"]
                for params in ({"page": 0}, {"pageSize": 0}, {"pageSize": 101}, {"page": "invalid"}):
                    invalid = client.get(path, params=params, headers=headers)
                    assert invalid.status_code == 422, invalid.text
        finally:
            database.DB_PATH = original_path


if __name__ == "__main__":
    test_redemption_code_credits_balance_once()
    test_personal_redemption_history_is_private_and_paginated()
