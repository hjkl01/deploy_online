from datetime import datetime, timezone
from config import Base, SessionLocal, engine, settings
from models import User, Env, Log
from security import encrypt_secret, hash_password
from sqlalchemy import text

def ensure_schema():
    Base.metadata.create_all(engine)

def init_database():
    ensure_schema()
    d = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - settings.log_retention_days * 86400
        d.query(Log).filter(Log.created_at.isnot(None), Log.created_at < datetime.fromtimestamp(cutoff, timezone.utc)).delete(synchronize_session=False)
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
