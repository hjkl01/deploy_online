from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship
from config import Base, now

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True)
    password_hash = Column(String(255))
    role = Column(String(20), default="viewer")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    description = Column(Text, default="")
    branch = Column(String(255), default="main")
    shell = Column(String(20), default="bash")
    enabled = Column(Boolean, default=True)
    steps = relationship("Step", cascade="all,delete-orphan", order_by="Step.position")
    envs = relationship("Env", cascade="all,delete-orphan")

class Step(Base):
    __tablename__ = "steps"
    id = Column(Integer, primary_key=True)
    project_id = Column(ForeignKey("projects.id"))
    name = Column(String(200))
    step_type = Column(String(30), default="command")
    cwd = Column(String(1000), default="~")
    command = Column(Text, default="")
    enabled = Column(Boolean, default=True)
    timeout = Column(Integer, default=3600)
    continue_on_error = Column(Boolean, default=False)
    position = Column(Integer, default=0)

class Env(Base):
    __tablename__ = "envs"
    id = Column(Integer, primary_key=True)
    project_id = Column(ForeignKey("projects.id"))
    key = Column(String(255))
    value = Column(Text, default="")
    is_secret = Column(Boolean, default=False)

class Deployment(Base):
    __tablename__ = "deployments"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, index=True)
    user_id = Column(Integer, index=True)
    status = Column(String(30), default="pending", index=True)
    exit_code = Column(Integer)
    created_at = Column(DateTime, default=now, index=True)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    config_snapshot = Column(Text)
    note = Column(Text, default="")
    cancel_requested = Column(Boolean, default=False, index=True)
    before_sha = Column(String(64))
    after_sha = Column(String(64))
    retry_of = Column(Integer)

    Index("ix_deployments_project_created", "project_id", "created_at")
    Index("ix_deployments_status_created", "status", "created_at")

class Log(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True)
    deployment_id = Column(Integer, index=True)
    step_id = Column(Integer, index=True)
    stream = Column(String(20))
    message = Column(Text)
    created_at = Column(DateTime, default=now, index=True)
