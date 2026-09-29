import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dependencies import dbdep, role
from models import Deployment, Env, Project, Step
from schemas import ProjectIn
from security import encrypt_secret
from services.repository import get_project, project_has_deployments, replace_project_children

router = APIRouter(prefix="/api/projects", tags=["projects"])


def validate_project(x: ProjectIn):
    if not x.name.strip() or len(x.name) > 200:
        raise HTTPException(400, "项目名称无效")
    if not x.branch.strip() or len(x.branch) > 255:
        raise HTTPException(400, "分支名称无效")
    if x.shell not in ("bash", "zsh") or not shutil.which(x.shell):
        raise HTTPException(400, f"shell 不可用: {x.shell}")

    home = Path.home().resolve()
    for step in x.steps:
        if step.step_type not in ("command", "git_pull", "restart", "health_check"):
            raise HTTPException(400, f"步骤类型无效: {step.step_type}")
        if step.step_type == "health_check" and not step.command.strip().startswith(("http://", "https://")):
            raise HTTPException(400, "health_check 的命令必须是 http:// 或 https:// URL")
        if step.cwd != "~" and not step.cwd.startswith("~/"):
            raise HTTPException(400, "cwd 必须从用户家目录 ~ 开始")
        relative = "" if step.cwd == "~" else step.cwd[2:]
        target = (home / relative).resolve()
        if target != home and home not in target.parents:
            raise HTTPException(400, "cwd 不能越出用户家目录")
        if len(step.name) > 200 or len(step.command) > 50000:
            raise HTTPException(400, "步骤名称或命令过长")
        if step.timeout < 1 or step.timeout > 86400:
            raise HTTPException(400, "步骤 timeout 必须在 1~86400 秒之间")

    for env in x.environment:
        if not env.key or "=" in env.key or "\x00" in env.key or len(env.key) > 255:
            raise HTTPException(400, "环境变量名无效")


def project_out(p):
    return {"id": p.id, "name": p.name, "description": p.description, "branch": p.branch, "shell": p.shell, "enabled": p.enabled}


def save_project(x, p, d):
    p.name, p.description, p.branch, p.shell, p.enabled = x.name, x.description, x.branch, x.shell, x.enabled
    existing_secret = {e.key: e.value for e in d.query(Env).filter_by(project_id=p.id, is_secret=True).all()}
    steps_data = [step.model_dump() for step in x.steps]
    env_data = []
    for env in x.environment:
        data = env.model_dump()
        if data["is_secret"] and data["value"] == "" and data["key"] in existing_secret:
            data["value"] = existing_secret[data["key"]]
        if data["is_secret"] and data["value"] and not data["value"].startswith("enc:"):
            data["value"] = encrypt_secret(data["value"])
        env_data.append(data)
    replace_project_children(d, p, steps_data, env_data)


@router.get("")
def projects(d: Session = Depends(dbdep), u=Depends(role("admin", "operator", "viewer"))):
    return [project_out(p) for p in d.query(Project).order_by(Project.id.desc())]


@router.get("/{pid}")
def project(pid: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator", "viewer"))):
    p = get_project(d, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    x = project_out(p)
    x["steps"] = [{"id": s.id, "name": s.name, "step_type": s.step_type, "cwd": s.cwd, "command": s.command, "enabled": s.enabled, "timeout": s.timeout, "continue_on_error": s.continue_on_error, "position": s.position} for s in p.steps]
    x["environment"] = [{"id": e.id, "key": e.key, "value": "" if e.is_secret else e.value, "is_secret": e.is_secret} for e in p.envs]
    return x


@router.post("")
def create_project(x: ProjectIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    validate_project(x)
    p = Project(name=x.name, description=x.description, branch=x.branch, shell=x.shell, enabled=x.enabled)
    d.add(p)
    d.flush()
    save_project(x, p, d)
    d.commit()
    d.refresh(p)
    return project_out(p)


@router.put("/{pid}")
def update_project(pid: int, x: ProjectIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    validate_project(x)
    p = d.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    save_project(x, p, d)
    d.commit()
    return project_out(p)


@router.delete("/{pid}")
def delete_project(pid: int, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    p = d.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    if project_has_deployments(d, pid):
        raise HTTPException(409, "项目已有部署记录，不能删除；如需保留历史记录，请先禁用项目")
    try:
        d.delete(p)
        d.commit()
    except IntegrityError:
        d.rollback()
        raise HTTPException(409, "项目存在关联数据，无法删除")
    return {"ok": True}


@router.get("/{pid}/yaml")
def yaml_export(pid: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator", "viewer"))):
    import yaml

    p = d.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    return yaml.safe_dump(
        {
            "name": p.name, "description": p.description, "enabled": p.enabled, "branch": p.branch, "shell": p.shell,
            "steps": [{"name": s.name, "type": s.step_type, "cwd": s.cwd, "command": s.command, "enabled": s.enabled, "timeout": s.timeout, "continue_on_error": s.continue_on_error} for s in p.steps],
            "environment": [{"key": e.key, "value": "***" if e.is_secret else e.value, "secret": e.is_secret} for e in p.envs],
        },
        allow_unicode=True,
        sort_keys=False,
    )
