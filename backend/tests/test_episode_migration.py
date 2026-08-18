from __future__ import annotations

from pathlib import Path
import sqlite3
import stat
import tempfile

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core import database
from app.services import artifact_service


# The schema as it existed before episodes: scenes hang off the project, and their asset
# columns hold signed URLs rather than paths.
LEGACY_SCHEMA = """
CREATE TABLE users (id integer primary key, created_at datetime, updated_at datetime, deleted_at datetime,
  username text, password text, role text, is_disabled numeric, balance_micros integer default 0,
  level integer default 1, user_group text default 'default');
CREATE TABLE projects (id text primary key, created_at datetime, updated_at datetime, deleted_at datetime,
  user_id integer, title text, original_script text, status text, video_url text, video_status text,
  video_progress integer, mode text default 'comic', aspect_ratio text default '9:16', width integer default 1080,
  height integer default 1920, fps integer default 24, target_duration_ms integer default 60000,
  language text default 'zh-CN', style_prompt text default '', negative_prompt text default '',
  current_stage text default 'script');
CREATE TABLE scenes (id text primary key, created_at datetime, updated_at datetime, deleted_at datetime,
  project_id text, order_num integer, narration text, visual_prompt text, image_url text,
  image_status text, audio_url text, audio_status text, audio_duration real default 0);
CREATE TABLE model_configs (id integer primary key, user_id integer, source text, created_at datetime,
  updated_at datetime, deleted_at datetime, provider text, encrypted_key text, is_active numeric,
  is_enabled numeric, purpose text, model_name text, is_verified numeric, name text, description text,
  base_url text, pricing_multiplier real, input_price_per_million real, output_price_per_million real,
  cache_read_price_per_million real, cache_write_price_per_million real, unit_price real, unit_name text);
CREATE TABLE chat_sessions (id text primary key, created_at datetime, updated_at datetime, deleted_at datetime,
  user_id integer, title text, config_id integer, official_config_id integer, provider text, model_name text);
CREATE TABLE chat_messages (id text primary key, session_id text, role text, content text, created_at datetime,
  provider text, model_name text);
CREATE TABLE usage_logs (id text primary key, created_at datetime, user_id integer, feature text,
  config_source text, config_id integer, provider text, model_name text, duration_ms integer,
  input_tokens integer, output_tokens integer, cache_read_tokens integer, cache_write_tokens integer,
  quantity real, cost_micros integer, pricing_multiplier real, input_price_per_million real,
  output_price_per_million real, cache_read_price_per_million real, cache_write_price_per_million real,
  unit_price real, unit_name text);
CREATE TABLE invitation_codes (id integer primary key, code text);
CREATE TABLE redemption_codes (id integer primary key, code text);
CREATE TABLE generation_jobs (id text primary key, created_at datetime, updated_at datetime, started_at datetime,
  finished_at datetime, user_id integer, project_id text, scene_id text, job_type text, status text,
  progress integer, input_json text, result_json text, attempt integer, max_attempts integer,
  idempotency_key text, lease_owner text, lease_expires_at datetime, heartbeat_at datetime,
  error_code text, error_message text);
INSERT INTO users VALUES (1,'t0','t0',NULL,'alice','x','user',0,0,1,'default');
INSERT INTO projects VALUES ('proj_old','t0','t1',NULL,1,'旧项目','从前有座山','done',NULL,'idle',0,
  'comic','9:16',1080,1920,24,60000,'zh-CN','','','script');
"""


def _upgrade_legacy_database(root: Path) -> tuple[sqlite3.Connection, str, str]:
    """Build a pre-episode database with real artifacts, then run the current init_db on it."""
    db_path = root / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(LEGACY_SCHEMA)
    connection.commit()
    connection.close()

    artifact_service.PRIVATE_GENERATED_DIR = root / "private_generated"
    image_path = artifact_service.store_artifact("projects", "proj_old", "s1.png", b"frame")
    audio_path = artifact_service.store_artifact("projects", "proj_old", "s1.mp3", b"voice")

    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO scenes VALUES ('sc1','t0','t0',NULL,'proj_old',1,'第一镜','山',?,'success',?,'success',3.5)",
        (
            artifact_service.signed_url_for_stored(image_path, "scene-1"),
            artifact_service.signed_url_for_stored(audio_path, "scene-1"),
        ),
    )
    connection.execute(
        "INSERT INTO scenes VALUES ('sc2','t0','t0',NULL,'proj_old',2,'第二镜','水',NULL,'idle',NULL,'idle',0)"
    )
    connection.execute(
        "INSERT INTO scenes VALUES ('sc3','t0','t0','t1','proj_old',3,'已删除','废',NULL,'idle',NULL,'idle',0)"
    )
    connection.commit()
    connection.close()

    database.DB_PATH = str(db_path)
    database._engines.pop(str(db_path), None)
    database.init_db()

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection, image_path, audio_path


def test_legacy_project_gains_episode_one_and_keeps_its_shots() -> None:
    original_db, original_dir = database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR
    try:
        with tempfile.TemporaryDirectory() as directory:
            connection, _, _ = _upgrade_legacy_database(Path(directory))
            episodes = connection.execute("SELECT * FROM episodes").fetchall()
            scenes = connection.execute("SELECT id, episode_id FROM scenes ORDER BY order_num").fetchall()
            connection.close()

            assert len(episodes) == 1
            assert episodes[0]["episode_number"] == 1
            # Scripted work carries over, and a project that already had shots lands past draft.
            assert episodes[0]["source_text"] == "从前有座山"
            assert episodes[0]["status"] == "storyboard"
            # Soft-deleted rows join too, so undeleting one does not produce an orphan.
            assert {row["episode_id"] for row in scenes} == {episodes[0]["id"]}
    finally:
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original_db, original_dir


def test_legacy_signed_urls_become_paths_that_still_resolve() -> None:
    original_db, original_dir = database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR
    try:
        with tempfile.TemporaryDirectory() as directory:
            connection, image_path, audio_path = _upgrade_legacy_database(Path(directory))
            scene = connection.execute("SELECT image_path, audio_path FROM scenes WHERE id='sc1'").fetchone()
            connection.close()

            assert (scene["image_path"], scene["audio_path"]) == (image_path, audio_path)
            assert not scene["image_path"].startswith("http")
            # The bytes are still reachable, which is the whole point of dropping the URL.
            assert artifact_service.artifact_absolute_path(scene["image_path"]).read_bytes() == b"frame"
    finally:
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original_db, original_dir


def test_upgrade_is_idempotent() -> None:
    original_db, original_dir = database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR
    try:
        with tempfile.TemporaryDirectory() as directory:
            connection, _, _ = _upgrade_legacy_database(Path(directory))
            connection.close()
            database.init_db()

            connection = sqlite3.connect(database.DB_PATH)
            connection.row_factory = sqlite3.Row
            episodes = connection.execute("SELECT COUNT(*) AS total FROM episodes").fetchone()["total"]
            connection.close()

            # A second startup must not hand the project a duplicate episode 1.
            assert episodes == 1
    finally:
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original_db, original_dir


def test_upgrade_records_revision_and_preserves_sqlite_settings() -> None:
    original_db, original_dir = database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR
    try:
        with tempfile.TemporaryDirectory() as directory:
            connection, _, _ = _upgrade_legacy_database(Path(directory))
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            connection.close()

            with database.engine().connect() as connection:
                foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
                busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()

            # Read from the migration tree rather than hard-coding the id: a literal here
            # silently goes stale the next time someone adds a revision, and did.
            assert revision == ScriptDirectory.from_config(Config(database.ALEMBIC_CONFIG)).get_current_head()
            assert foreign_keys == 1
            assert busy_timeout == 30_000
            assert stat.S_IMODE(Path(database.DB_PATH).stat().st_mode) == 0o600
    finally:
        database.DB_PATH, artifact_service.PRIVATE_GENERATED_DIR = original_db, original_dir


def test_config_verification_removal_keeps_only_verified_configs_enabled() -> None:
    original_db = database.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config-migration.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);
                INSERT INTO alembic_version VALUES ('345000649eb5');
                CREATE TABLE model_configs (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, user_id INTEGER, provider TEXT NOT NULL,
                    encrypted_key TEXT NOT NULL, is_active NUMERIC, is_enabled NUMERIC, purpose TEXT,
                    model_name TEXT, is_verified NUMERIC, name TEXT, description TEXT, base_url TEXT
                );
                CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL, password TEXT NOT NULL);
                INSERT INTO model_configs VALUES (1, 'official', NULL, 'openai', 'key', 1, 1, 'script', 'a', 1, '', '', '');
                INSERT INTO model_configs VALUES (2, 'official', NULL, 'openai', '', 1, 1, 'script', 'b', 0, '', '', '');
                """
            )
            connection.commit()
            connection.close()

            database.DB_PATH = str(path)
            database._engines.pop(str(path), None)
            config = Config(database.ALEMBIC_CONFIG)
            with database.engine().connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")

            connection = sqlite3.connect(path)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(model_configs)")}
            statuses = connection.execute("SELECT id, is_active, is_enabled FROM model_configs ORDER BY id").fetchall()
            connection.close()

            assert "is_verified" not in columns
            assert statuses == [(1, 1, 1), (2, 0, 0)]
    finally:
        database.DB_PATH = original_db


if __name__ == "__main__":
    test_legacy_project_gains_episode_one_and_keeps_its_shots()
    test_legacy_signed_urls_become_paths_that_still_resolve()
    test_upgrade_is_idempotent()
    test_upgrade_records_revision_and_preserves_sqlite_settings()
    test_config_verification_removal_keeps_only_verified_configs_enabled()
