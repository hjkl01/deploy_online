from datetime import datetime, timezone
from pathlib import Path

from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
    database_url: str = "sqlite:///./data/deploy_online.db"
    secret_key: str = "change-me"
    admin_username: str = "admin"
    admin_password: str = "admin"
    log_retention_days: int = 30
    worker_concurrency: int = 4

settings = Settings()

if settings.secret_key == "change-me":
    raise RuntimeError("SECRET_KEY 未配置，请在 .env 中设置随机长字符串")
if settings.admin_password == "admin":
    raise RuntimeError("ADMIN_PASSWORD 未配置，请在 .env 中设置管理员密码")

Path("data").mkdir(exist_ok=True)
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30},
)

@event.listens_for(engine, "connect")
def configure_sqlite(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()
now = lambda: datetime.now(timezone.utc)
