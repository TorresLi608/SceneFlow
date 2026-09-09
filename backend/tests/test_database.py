from __future__ import annotations

from contextlib import chdir
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from unittest.mock import patch

import bcrypt
from sqlmodel import Session, SQLModel, select

from app.core import config, database
from app.core.database import SUPER_ADMIN_PASSWORD, SUPER_ADMIN_USERNAME, seed_super_admin
from app.models import User


def _session() -> Session:
    engine = database._build_engine(":memory:")
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
    assert bcrypt.checkpw(SUPER_ADMIN_PASSWORD.encode(), user.password.encode())


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
            role="superAdmin",
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


def test_database_and_admin_environment_configuration() -> None:
    config_file = Path(config.__file__).resolve()
    with tempfile.TemporaryDirectory() as directory, chdir(directory), patch("dotenv.load_dotenv"):
        for environment in ({}, {"DATABASE_URL": ""}):
            with patch.dict(os.environ, environment, clear=True):
                defaults = runpy.run_path(str(config_file))
            assert defaults["DB_PATH"] == str(config_file.parents[3] / "data" / "app.db")
            assert defaults["SUPER_ADMIN_USERNAME"] == "superAdmin"

        for url in ("sqlite://", "sqlite:///:memory:", "sqlite:////app/data/app.db"):
            with patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
                values = runpy.run_path(str(config_file))
            assert values["DB_PATH"] == ("/app/data/app.db" if "app.db" in url else ":memory:")

        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///custom/app.db", "SCENEFLOW_SUPER_ADMIN_USERNAME": "  site-owner  "}, clear=True):
            values = runpy.run_path(str(config_file))
        assert values["DB_PATH"] == "custom/app.db"
        assert values["SUPER_ADMIN_USERNAME"] == "site-owner"

        for environment in (
            {"SCENEFLOW_SUPER_ADMIN_USERNAME": ""},
            {"SCENEFLOW_SUPER_ADMIN_USERNAME": "ab"},
            {"SCENEFLOW_SUPER_ADMIN_USERNAME": "a" * 65},
            {"DATABASE_URL": "postgresql://localhost/app"},
            {"DATABASE_URL": "sqlite:///file:app.db?uri=true"},
            {"SCENEFLOW_ENV": "production"},
        ):
            with patch.dict(os.environ, environment, clear=True):
                try:
                    runpy.run_path(str(config_file))
                except RuntimeError:
                    pass
                else:
                    raise AssertionError(f"invalid configuration accepted: {tuple(environment)}")


def test_restart_keeps_database_and_renames_default_admin() -> None:
    # Separate interpreters exercise real config loading, directory creation, and Alembic startup.
    script = """
import bcrypt
import sys
from fastapi import HTTPException
from sqlmodel import select
from app.api.v1.auth import login
from app.core.database import db, engine, init_db
from app.models import User

init_db()
if sys.argv[1] == 'write':
    with engine().connect() as connection:
        assert connection.exec_driver_sql('PRAGMA journal_mode=WAL').scalar_one() == 'wal'
    with db() as session:
        user = session.exec(select(User)).one()
        user.nickname = 'persisted'
        user.balance_micros = 12345
        user.password = bcrypt.hashpw(b'changed-password', bcrypt.gensalt()).decode()
        session.add(user)
else:
    init_db()
    result = login({'username': 'site-owner', 'password': 'changed-password'})
    assert result['user']['id'] == 1
    with db() as session:
        user = session.exec(select(User)).one()
        assert (user.username, user.nickname, user.balance_micros) == ('site-owner', 'persisted', 12345)
    try:
        login({'username': 'superAdmin', 'password': 'changed-password'})
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError('the default admin login must no longer work')
"""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "nested" / "data" / "app.db"
        environment = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{path}",
            "SCENEFLOW_PRIVATE_GENERATED_DIR": str(Path(directory) / "media"),
            "SCENEFLOW_ENV": "development",
            "SCENEFLOW_SUPER_ADMIN_PASSWORD": "initial-test-password",
        }
        for phase, username in (("write", "superAdmin"), ("read", "site-owner")):
            result = subprocess.run(
                [sys.executable, "-c", script, phase],
                cwd=Path(__file__).resolve().parents[1],
                env={**environment, "SCENEFLOW_SUPER_ADMIN_USERNAME": username},
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
        assert path.is_file()
        assert path.stat().st_mode & 0o777 == 0o600


def test_seed_custom_admin_and_reject_username_collisions() -> None:
    with patch.object(database, "SUPER_ADMIN_USERNAME", "site-owner"):
        with _session() as session:
            seed_super_admin(session)
            session.flush()
            user = session.exec(select(User)).one()
            assert user.username == "site-owner" and user.role == "superAdmin"
            with patch.object(database, "SUPER_ADMIN_USERNAME", "another-owner"):
                try:
                    seed_super_admin(session)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("a later config change must not silently create a second admin")
            assert len(session.exec(select(User)).all()) == 1

        for with_legacy in (False, True):
            with _session() as session:
                session.add(User(username="site-owner", password="unchanged", role="user"))
                if with_legacy:
                    session.add(User(username="superAdmin", password="legacy", role="superAdmin"))
                session.flush()
                try:
                    seed_super_admin(session)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("an occupied username must not be promoted or overwrite another account")
                user = session.exec(select(User).where(User.username == "site-owner")).one()
                assert user.role == "user" and user.password == "unchanged"


if __name__ == "__main__":
    test_seed_super_admin_creates_missing_user()
    test_seed_super_admin_keeps_existing_password()
    test_database_and_admin_environment_configuration()
    test_restart_keeps_database_and_renames_default_admin()
    test_seed_custom_admin_and_reject_username_collisions()
