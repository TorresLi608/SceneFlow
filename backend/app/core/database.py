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
from app.core.config import DB_PATH, SUPER_ADMIN_PASSWORD
from app.models import User
from app.utils.common import now


SUPER_ADMIN_USERNAME = "superAdmin"
ALEMBIC_CONFIG = Path(__file__).resolve().parents[2] / "alembic.ini"

_engines: dict[str, Engine] = {}


def _apply_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 30000")
    cursor.close()


def _build_engine(path: str) -> Engine:
    if path == ":memory:":
        # A pooled in-memory database would hand out a different empty database per connection.
        built = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        built = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30, "check_same_thread": False})
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
    if user:
        user.role = "superAdmin"
        user.is_disabled = False
        user.deleted_at = None
        user.updated_at = stamp
        session.add(user)
        return
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
