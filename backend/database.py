from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from config import SessionLocal, engine, settings
from models import User, Env, Log
from security import encrypt_secret, hash_password

BASE_TABLES = {"users", "projects", "steps", "envs", "deployments", "deployment_steps", "logs"}


def _alembic_config():
    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parent / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def _schema_matches_models():
    inspector = inspect(engine)
    expected = {
        "users": {"id", "username", "password_hash", "role"},
        "projects": {"id", "name", "description", "branch", "shell", "enabled"},
        "steps": {"id", "project_id", "name", "step_type", "cwd", "command", "enabled", "timeout", "continue_on_error", "position"},
        "envs": {"id", "project_id", "key", "value", "is_secret"},
        "deployments": {"id", "project_id", "user_id", "status", "exit_code", "created_at", "started_at", "finished_at", "config_snapshot", "note", "cancel_requested", "before_sha", "after_sha", "retry_of"},
        "deployment_steps": {"id", "deployment_id", "source_step_id", "position", "name", "status", "started_at", "finished_at", "exit_code", "duration_ms", "error"},
        "logs": {"id", "deployment_id", "step_id", "stream", "message", "created_at"},
    }
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    if tables != BASE_TABLES:
        return False
    return all(columns <= {column["name"] for column in inspector.get_columns(table)} for table, columns in expected.items())


def migrate_database():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    config = _alembic_config()
    if "alembic_version" not in tables:
        app_tables = tables & BASE_TABLES
        if not app_tables:
            command.upgrade(config, "head")
            return
        if not _schema_matches_models():
            raise RuntimeError(
                "现有数据库结构与当前模型不兼容，无法自动接管。请先备份数据库，并检查缺失的表或字段。"
            )
        command.stamp(config, "0001_initial")
        command.upgrade(config, "head")
        return
    command.upgrade(config, "head")


def ensure_schema():
    migrate_database()


def init_database():
    ensure_schema()
    d = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - settings.log_retention_days * 86400
        d.query(Log).filter(
            Log.created_at.isnot(None),
            Log.created_at < datetime.fromtimestamp(cutoff, timezone.utc),
        ).delete(synchronize_session=False)
        for env in d.query(Env).filter_by(is_secret=True).all():
            if env.value and not env.value.startswith("enc:"):
                env.value = encrypt_secret(env.value)
        if not d.query(User).first():
            d.add(User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            ))
        d.commit()
    finally:
        d.close()
