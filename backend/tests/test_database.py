from __future__ import annotations

import bcrypt
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.database import SUPER_ADMIN_USERNAME, seed_super_admin
from app.models import User


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_seed_super_admin_creates_missing_user() -> None:
    session = _session()
    seed_super_admin(session)
    session.flush()
    user = session.exec(select(User).where(User.username == SUPER_ADMIN_USERNAME)).first()

    assert user is not None
    assert user.role == "superAdmin"
    assert not bool(user.is_disabled)
    assert bcrypt.checkpw(b"superAdmin@123", user.password.encode())


def test_seed_super_admin_keeps_existing_password() -> None:
    session = _session()
    password = bcrypt.hashpw(b"changed-password", bcrypt.gensalt()).decode()
    session.add(
        User(
            created_at="old",
            updated_at="old",
            deleted_at="old",
            username=SUPER_ADMIN_USERNAME,
            password=password,
            role="user",
            is_disabled=True,
        )
    )
    session.flush()

    seed_super_admin(session)
    session.flush()
    user = session.exec(select(User).where(User.username == SUPER_ADMIN_USERNAME)).first()

    assert user is not None
    assert user.password == password
    assert user.role == "superAdmin"
    assert not bool(user.is_disabled)
    assert user.deleted_at is None


if __name__ == "__main__":
    test_seed_super_admin_creates_missing_user()
    test_seed_super_admin_keeps_existing_password()
