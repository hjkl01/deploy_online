from datetime import datetime, timezone
from pathlib import Path
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

class Settings(BaseSettings):
 model_config={"env_file":".env","env_file_encoding":"utf-8","extra":"ignore"}
 database_url:str="sqlite:///./data/deploy_online.db"
 secret_key:str="change-me"
 admin_username:str="admin"
 admin_password:str="admin"
 log_retention_days:int=30

settings=Settings()
Path("data").mkdir(exist_ok=True)
engine=create_engine(settings.database_url,connect_args={"check_same_thread":False,"timeout":30})
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
Base=declarative_base()
now=lambda:datetime.now(timezone.utc)
