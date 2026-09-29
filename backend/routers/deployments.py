import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import now
from dependencies import dbdep, role, user
from models import Deployment, DeploymentStep, Log, Project, User
from services.deployment import snapshot_project
from services.repository import get_deployment, get_deployment_with_names, list_deployment_logs, list_deployment_steps

router = APIRouter(prefix="/api", tags=["deployments"])


@router.post("/projects/{pid}/deploy")
def deploy(pid: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator"))):
    p = d.get(Project, pid)
    if not p or not p.enabled:
        raise HTTPException(404, "项目不存在或已禁用")
    job = Deployment(project_id=pid, user_id=u.id, config_snapshot=snapshot_project(p))
    d.add(job)
    d.flush()
    for i, step in enumerate(p.steps):
        if step.enabled:
            d.add(DeploymentStep(deployment_id=job.id, source_step_id=step.id, position=i, name=step.name))
    d.commit()
    d.refresh(job)
    return {"id": job.id, "status": "pending"}


@router.get("")
def deployments(project_id: int | None = None, status: str | None = None, page: int = 1, page_size: int = 20, d: Session = Depends(dbdep), u=Depends(user)):
    page, page_size = max(1, page), max(1, min(page_size, 100))
    if status is not None and status not in ("pending", "running", "success", "failed", "cancelled"):
        raise HTTPException(400, "状态无效")
    q = d.query(Deployment, Project.name, User.username).outerjoin(Project, Project.id == Deployment.project_id).outerjoin(User, User.id == Deployment.user_id)
    if project_id is not None:
        q = q.filter(Deployment.project_id == project_id)
    if status is not None:
        q = q.filter(Deployment.status == status)
    total = q.count()
    rows = q.order_by(Deployment.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [
        {"id": j.id, "project_id": j.project_id, "project_name": project_name or f"项目 #{j.project_id}", "user_id": j.user_id, "username": username or "-", "status": j.status, "exit_code": j.exit_code, "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at}
        for j, project_name, username in rows
    ]}


@router.get("/{did}")
def deployment(did: int, d: Session = Depends(dbdep), u=Depends(user)):
    row = get_deployment_with_names(d, did)
    if not row:
        raise HTTPException(404, "部署不存在")
    j, project_name, username = row
    steps = list_deployment_steps(d, did)
    return {"id": j.id, "project_id": j.project_id, "project_name": project_name or f"项目 #{j.project_id}", "user_id": j.user_id, "username": username or "-", "status": j.status, "exit_code": j.exit_code, "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at, "note": j.note, "before_sha": j.before_sha, "after_sha": j.after_sha, "retry_of": j.retry_of, "steps": [{"id": s.id, "source_step_id": s.source_step_id, "position": s.position, "name": s.name, "status": s.status, "started_at": s.started_at, "finished_at": s.finished_at, "exit_code": s.exit_code, "duration_ms": s.duration_ms, "error": s.error} for s in steps]}


@router.get("/{did}/logs")
def logs(did: int, d: Session = Depends(dbdep), u=Depends(user)):
    return [{"id": x.id, "step_id": x.step_id, "stream": x.stream, "message": x.message} for x in list_deployment_logs(d, did)]


@router.post("/{did}/cancel")
def cancel_deployment(did: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator"))):
    j = get_deployment(d, did)
    if not j:
        raise HTTPException(404, "部署不存在")
    if j.status not in ("pending", "running"):
        raise HTTPException(409, "部署已经结束")
    j.cancel_requested = True
    if j.status == "pending":
        j.status, j.exit_code, j.finished_at = "cancelled", 130, now()
        for step in d.query(DeploymentStep).filter_by(deployment_id=did, status="pending").all():
            step.status, step.finished_at, step.exit_code, step.error = "cancelled", j.finished_at, 130, "部署取消"
    d.commit()
    return {"ok": True, "status": j.status}


@router.post("/{did}/retry")
def retry_deployment(did: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator"))):
    old = get_deployment(d, did)
    if not old:
        raise HTTPException(404, "部署不存在")
    if old.status not in ("failed", "cancelled"):
        raise HTTPException(409, "只有失败或取消的部署可以重试")
    job = Deployment(project_id=old.project_id, user_id=u.id, status="pending", config_snapshot=old.config_snapshot, note=old.note, retry_of=old.id)
    d.add(job)
    d.flush()
    snapshot = json.loads(job.config_snapshot or "{}")
    for i, step in enumerate(snapshot.get("steps", [])):
        if step.get("enabled"):
            d.add(DeploymentStep(deployment_id=job.id, source_step_id=step.get("id"), position=i, name=step.get("name", "")))
    d.commit()
    d.refresh(job)
    return {"id": job.id, "status": job.status, "retry_of": old.id}


@router.post("/{did}/note")
def update_deployment_note(did: int, note: str, d: Session = Depends(dbdep), u=Depends(role("admin", "operator"))):
    j = d.get(Deployment, did)
    if not j:
        raise HTTPException(404, "部署不存在")
    j.note = note[:2000]
    d.commit()
    return {"ok": True, "note": j.note}
