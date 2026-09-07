from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from alembic import command
from alembic.config import Config
import bcrypt
from sqlalchemy import Engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

import app.models  # noqa: F401 -- register every table before Alembic loads metadata
from app.core.config import DATABASE_URL, DB_PATH, SUPER_ADMIN_PASSWORD, SUPER_ADMIN_USERNAME
from app.models import User
from app.utils.common import now


ALEMBIC_CONFIG = Path(__file__).resolve().parents[2] / "alembic.ini"

_engines: dict[str, Engine] = {}


def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 30000")
    cursor.close()


def _build_engine(path: str) -> Engine:
    url = DATABASE_URL.set(database=path)
    if path == ":memory:":
        # A pooled in-memory database would hand out a different empty database per connection.
        built = create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        Path(path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        built = create_engine(url, connect_args={"timeout": 30, "check_same_thread": False})
    event.listen(built, "connect", _apply_pragmas)
    return built


def engine() -> Engine:
    # Built lazily and cached per path because tests point DB_PATH at temporary files.
    path = str(DB_PATH)
    if path not in _engines:
        _engines[path] = _build_engine(path)
    return _engines[path]


@contextmanager
def db() -> Iterator[Session]:
    session = Session(engine(), expire_on_commit=False)
    try:
        yield session
        session.commit()
    finally:
        session.close()


def init_db() -> None:
    config = Config(ALEMBIC_CONFIG)
    with engine().connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with db() as session:
        seed_super_admin(session)
    path = Path(str(DB_PATH))
    if str(DB_PATH) != ":memory:" and path.is_file():
        path.chmod(0o600)


def seed_super_admin(session: Session) -> None:
    stamp = now()
    user = session.exec(select(User).where(User.username == SUPER_ADMIN_USERNAME)).first()
    if SUPER_ADMIN_USERNAME != "superAdmin":
        legacy = session.exec(select(User).where(User.username == "superAdmin", User.role == "superAdmin")).first()
        if legacy:
            if user:
                raise RuntimeError("SCENEFLOW_SUPER_ADMIN_USERNAME is already in use; choose an unused username")
            # Keep the original ID, password, and ownership; do not leave the default login enabled.
            user = legacy
            user.username = SUPER_ADMIN_USERNAME
    if user:
        if user.role != "superAdmin":
            raise RuntimeError("SCENEFLOW_SUPER_ADMIN_USERNAME belongs to a non-admin user")
        user.is_disabled = False
        user.deleted_at = None
        user.updated_at = stamp
        session.add(user)
        return
    if session.exec(select(User.id).where(User.role == "superAdmin")).first() is not None:
        raise RuntimeError("SCENEFLOW_SUPER_ADMIN_USERNAME does not match an existing admin; rename that account explicitly")
    password = bcrypt.hashpw(SUPER_ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode()
    session.add(
        User(
            created_at=stamp,
            updated_at=stamp,
            username=SUPER_ADMIN_USERNAME,
            password=password,
            role="superAdmin",
            is_disabled=False,
        )
    )
