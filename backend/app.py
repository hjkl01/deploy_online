import asyncio
import shutil
import time
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from config import SessionLocal, now, settings
from database import init_database
from models import Deployment, DeploymentStep, Env, Log, Project, Step, User
from runtime import login_attempts, queues
from schemas import EnvIn, Login, ProjectIn, StepIn, UserIn
from security import encrypt_secret, hash_password, verify_password
from services.deployment import snapshot_project

init_database()

app = FastAPI(title="deploy_online")
STATIC_DIR = Path(__file__).resolve().parent / "static"
if (STATIC_DIR / "_next").is_dir():
    app.mount("/_next", StaticFiles(directory=STATIC_DIR / "_next"), name="next")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=86400,
    same_site="lax",
    https_only=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def dbdep():
    d = SessionLocal()
    try:
        yield d
    finally:
        d.close()

def user(request: Request, d: Session = Depends(dbdep)):
    user_id = request.session.get("user_id")
    u = d.get(User, user_id) if user_id else None
    if not u:
        raise HTTPException(401, "未登录")
    return u

def role(*roles):
    def dep(u=Depends(user)):
        if u.role not in roles:
            raise HTTPException(403, "没有权限")
        return u
    return dep

def validate_project(x: ProjectIn):
    if not x.name.strip() or len(x.name) > 200:
        raise HTTPException(400, "项目名称无效")
    if not x.branch.strip() or len(x.branch) > 255:
        raise HTTPException(400, "分支名称无效")
    if x.shell not in ("bash", "zsh") or not shutil.which(x.shell):
        raise HTTPException(400, f"shell 不可用: {x.shell}")

    home = Path.home().resolve()
    for step in x.steps:
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
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "branch": p.branch,
        "shell": p.shell,
        "enabled": p.enabled,
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/auth/login")
def login(x: Login, request: Request, d: Session = Depends(dbdep)):
    key = f"{request.client.host if request.client else '-'}:{x.username}"
    now_ts = time.time()
    login_attempts[key] = [t for t in login_attempts[key] if now_ts - t < 60]
    if len(login_attempts[key]) >= 5:
        raise HTTPException(429, "登录失败次数过多，请 1 分钟后再试")

    u = d.query(User).filter_by(username=x.username).first()
    if not u or not verify_password(x.password, u.password_hash):
        login_attempts[key].append(now_ts)
        raise HTTPException(401, "用户名或密码错误")

    login_attempts.pop(key, None)
    request.session["user_id"] = u.id
    return {"id": u.id, "username": u.username, "role": u.role}

@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@app.get("/api/auth/me")
def me(u=Depends(user)):
    return {"id": u.id, "username": u.username, "role": u.role}

@app.get("/api/users")
def users(d: Session = Depends(dbdep), u=Depends(role("admin"))):
    return [{"id": x.id, "username": x.username, "role": x.role} for x in d.query(User).order_by(User.id)]

@app.post("/api/users")
def create_user(x: UserIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    username = x.username.strip()
    if not username or not x.password:
        raise HTTPException(400, "用户名和密码不能为空")
    if x.role not in ("admin", "operator", "viewer"):
        raise HTTPException(400, "角色无效")
    if len(x.password.encode()) > 72:
        raise HTTPException(400, "密码不能超过 72 字节")
    if d.query(User).filter_by(username=username).first():
        raise HTTPException(409, "用户名已存在")
    v = User(username=username, password_hash=hash_password(x.password), role=x.role)
    d.add(v)
    d.commit()
    d.refresh(v)
    return {"id": v.id, "username": v.username, "role": v.role}

@app.put("/api/users/{uid}")
def update_user(uid: int, x: UserIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    username = x.username.strip()
    v = d.get(User, uid)
    if not v:
        raise HTTPException(404, "用户不存在")
    if not username or x.role not in ("admin", "operator", "viewer"):
        raise HTTPException(400, "用户信息无效")
    if d.query(User).filter(User.username == username, User.id != uid).first():
        raise HTTPException(409, "用户名已存在")
    v.username = username
    v.role = x.role
    if x.password:
        if len(x.password.encode()) > 72:
            raise HTTPException(400, "密码不能超过 72 字节")
        v.password_hash = hash_password(x.password)
    d.commit()
    return {"id": v.id, "username": v.username, "role": v.role}

@app.delete("/api/users/{uid}")
def delete_user(uid: int, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    if uid == u.id:
        raise HTTPException(400, "不能删除当前登录用户")
    v = d.get(User, uid)
    if not v:
        raise HTTPException(404, "用户不存在")
    if v.role == "admin" and d.query(User).filter_by(role="admin").count() <= 1:
        raise HTTPException(400, "至少保留一个管理员")
    d.delete(v)
    d.commit()
    return {"ok": True}

@app.get("/api/projects")
def projects(d: Session = Depends(dbdep), u=Depends(role("admin", "operator", "viewer"))):
    return [project_out(p) for p in d.query(Project).order_by(Project.id.desc())]

@app.get("/api/projects/{pid}")
def project(pid: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator", "viewer"))):
    p = d.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    x = project_out(p)
    x["steps"] = [
        {
            "id": s.id,
            "name": s.name,
            "step_type": s.step_type,
            "cwd": s.cwd,
            "command": s.command,
            "enabled": s.enabled,
            "timeout": s.timeout,
            "continue_on_error": s.continue_on_error,
            "position": s.position,
        }
        for s in p.steps
    ]
    x["environment"] = [
        {"id": e.id, "key": e.key, "value": "" if e.is_secret else e.value, "is_secret": e.is_secret}
        for e in p.envs
    ]
    return x

def save_project(x, p, d):
    p.name = x.name
    p.description = x.description
    p.branch = x.branch
    p.shell = x.shell
    p.enabled = x.enabled
    existing_secret = {
        e.key: e.value for e in d.query(Env).filter_by(project_id=p.id, is_secret=True).all()
    }
    d.query(Step).filter_by(project_id=p.id).delete()
    d.query(Env).filter_by(project_id=p.id).delete()
    for i, step in enumerate(x.steps):
        d.add(Step(project_id=p.id, position=i, **step.model_dump()))
    for env in x.environment:
        data = env.model_dump()
        if data["is_secret"] and data["value"] == "" and data["key"] in existing_secret:
            data["value"] = existing_secret[data["key"]]
        if data["is_secret"] and data["value"] and not data["value"].startswith("enc:"):
            data["value"] = encrypt_secret(data["value"])
        d.add(Env(project_id=p.id, **data))

@app.post("/api/projects")
def create_project(x: ProjectIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    validate_project(x)
    p = Project(name=x.name, description=x.description, branch=x.branch, shell=x.shell, enabled=x.enabled)
    d.add(p)
    d.flush()
    save_project(x, p, d)
    d.commit()
    d.refresh(p)
    return project_out(p)

@app.put("/api/projects/{pid}")
def update_project(pid: int, x: ProjectIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    validate_project(x)
    p = d.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    save_project(x, p, d)
    d.commit()
    return project_out(p)

@app.delete("/api/projects/{pid}")
def delete_project(pid: int, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    p = d.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    d.delete(p)
    d.commit()
    return {"ok": True}

@app.post("/api/projects/{pid}/deploy")
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

@app.get("/api/deployments")
def deployments(
    project_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    d: Session = Depends(dbdep),
    u=Depends(user),
):
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    valid_status = ("pending", "running", "success", "failed", "cancelled")
    if status is not None and status not in valid_status:
        raise HTTPException(400, "状态无效")
    q = (
        d.query(Deployment, Project.name, User.username)
        .outerjoin(Project, Project.id == Deployment.project_id)
        .outerjoin(User, User.id == Deployment.user_id)
    )
    if project_id is not None:
        q = q.filter(Deployment.project_id == project_id)
    if status is not None:
        q = q.filter(Deployment.status == status)
    total = q.count()
    rows = q.order_by(Deployment.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": j.id,
                "project_id": j.project_id,
                "project_name": project_name or f"项目 #{j.project_id}",
                "user_id": j.user_id,
                "username": username or "-",
                "status": j.status,
                "exit_code": j.exit_code,
                "created_at": j.created_at,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
            }
            for j, project_name, username in rows
        ],
    }

@app.get("/api/deployments/{did}")
def deployment(did: int, d: Session = Depends(dbdep), u=Depends(user)):
    row = (
        d.query(Deployment, Project.name, User.username)
        .outerjoin(Project, Project.id == Deployment.project_id)
        .outerjoin(User, User.id == Deployment.user_id)
        .filter(Deployment.id == did)
        .first()
    )
    if not row:
        raise HTTPException(404, "部署不存在")
    j, project_name, username = row
    step_rows = d.query(DeploymentStep).filter_by(deployment_id=did).order_by(DeploymentStep.position).all()
    return {
        "id": j.id,
        "project_id": j.project_id,
        "project_name": project_name or f"项目 #{j.project_id}",
        "user_id": j.user_id,
        "username": username or "-",
        "status": j.status,
        "exit_code": j.exit_code,
        "created_at": j.created_at,
        "started_at": j.started_at,
        "finished_at": j.finished_at,
        "note": j.note,
        "before_sha": j.before_sha,
        "after_sha": j.after_sha,
        "retry_of": j.retry_of,
        "steps": [{"id": s.id, "source_step_id": s.source_step_id, "position": s.position, "name": s.name, "status": s.status, "started_at": s.started_at, "finished_at": s.finished_at, "exit_code": s.exit_code, "duration_ms": s.duration_ms, "error": s.error} for s in step_rows],
    }

@app.get("/api/deployments/{did}/logs")
def logs(did: int, d: Session = Depends(dbdep), u=Depends(user)):
    return [
        {"id": x.id, "step_id": x.step_id, "stream": x.stream, "message": x.message}
        for x in d.query(Log).filter_by(deployment_id=did).order_by(Log.id)
    ]

@app.post("/api/deployments/{did}/cancel")
def cancel_deployment(did: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator"))):
    j = d.get(Deployment, did)
    if not j:
        raise HTTPException(404, "部署不存在")
    if j.status not in ("pending", "running"):
        raise HTTPException(409, "部署已经结束")
    j.cancel_requested = True
    if j.status == "pending":
        j.status = "cancelled"
        j.exit_code = 130
        j.finished_at = now()
    d.commit()
    return {"ok": True, "status": j.status}

@app.post("/api/deployments/{did}/retry")
def retry_deployment(did: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator"))):
    old = d.get(Deployment, did)
    if not old:
        raise HTTPException(404, "部署不存在")
    if old.status not in ("failed", "cancelled"):
        raise HTTPException(409, "只有失败或取消的部署可以重试")
    job = Deployment(
        project_id=old.project_id,
        user_id=u.id,
        status="pending",
        config_snapshot=old.config_snapshot,
        note=old.note,
        retry_of=old.id,
    )
    d.add(job)
    d.flush()
    snapshot = __import__("json").loads(job.config_snapshot or "{}")
    for i, step in enumerate(snapshot.get("steps", [])):
        if step.get("enabled"):
            d.add(DeploymentStep(deployment_id=job.id, source_step_id=step.get("id"), position=i, name=step.get("name", "")))
    d.commit()
    d.refresh(job)
    return {"id": job.id, "status": job.status, "retry_of": old.id}

@app.post("/api/deployments/{did}/note")
def update_deployment_note(
    did: int,
    note: str,
    d: Session = Depends(dbdep),
    u=Depends(role("admin", "operator")),
):
    j = d.get(Deployment, did)
    if not j:
        raise HTTPException(404, "部署不存在")
    j.note = note[:2000]
    d.commit()
    return {"ok": True, "note": j.note}

@app.get("/api/projects/{pid}/yaml")
def yaml_export(pid: int, d: Session = Depends(dbdep), u=Depends(role("admin", "operator", "viewer"))):
    p = d.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    return yaml.safe_dump(
        {
            "name": p.name,
            "description": p.description,
            "enabled": p.enabled,
            "branch": p.branch,
            "shell": p.shell,
            "steps": [
                {
                    "name": s.name,
                    "type": s.step_type,
                    "cwd": s.cwd,
                    "command": s.command,
                    "enabled": s.enabled,
                    "timeout": s.timeout,
                    "continue_on_error": s.continue_on_error,
                }
                for s in p.steps
            ],
            "environment": [
                {"key": e.key, "value": "***" if e.is_secret else e.value, "secret": e.is_secret}
                for e in p.envs
            ],
        },
        allow_unicode=True,
        sort_keys=False,
    )

@app.websocket("/ws/deployments/{did}")
async def ws(w: WebSocket, did: int):
    if not w.scope.get("session", {}).get("user_id"):
        await w.close(code=1008)
        return
    d = SessionLocal()
    job = d.get(Deployment, did)
    rows = d.query(Log).filter_by(deployment_id=did).order_by(Log.id).all()
    d.close()
    if not job:
        await w.close(code=1008)
        return

    await w.accept()
    q = asyncio.Queue()
    queues[did].add(q)
    try:
        initial_steps = d.query(DeploymentStep).filter_by(deployment_id=did).order_by(DeploymentStep.position).all()
        await w.send_json({
            "type": "connected",
            "deployment_id": did,
            "status": job.status,
            "exit_code": job.exit_code,
            "steps": [{"id": s.id, "name": s.name, "status": s.status, "started_at": s.started_at, "finished_at": s.finished_at, "exit_code": s.exit_code, "duration_ms": s.duration_ms, "error": s.error} for s in initial_steps],
        })
        await w.send_json({
            "type": "snapshot",
            "logs": [
                {"id": x.id, "step_id": x.step_id, "stream": x.stream, "message": x.message}
                for x in rows
            ],
        })
        last_log = rows[-1].id if rows else 0
        while True:
            try:
                await w.send_json(await asyncio.wait_for(q.get(), 2))
            except asyncio.TimeoutError:
                d = SessionLocal()
                try:
                    job = d.get(Deployment, did)
                    step_rows = d.query(DeploymentStep).filter_by(deployment_id=did).order_by(DeploymentStep.position).all()
                    new = (
                        d.query(Log)
                        .filter(Log.deployment_id == did, Log.id > last_log)
                        .order_by(Log.id)
                        .all()
                    )
                    last_log = new[-1].id if new else last_log
                    for x in new:
                        await w.send_json({
                            "type": "log",
                            "id": x.id,
                            "step_id": x.step_id,
                            "stream": x.stream,
                            "message": x.message,
                        })
                    if job:
                        await w.send_json({
                            "type": "status",
                            "status": job.status,
                            "exit_code": job.exit_code,
                            "steps": [{"id": s.id, "name": s.name, "status": s.status, "started_at": s.started_at, "finished_at": s.finished_at, "exit_code": s.exit_code, "duration_ms": s.duration_ms, "error": s.error} for s in step_rows],
                        })
                        if job.status in ("success", "failed", "cancelled"):
                            break
                finally:
                    d.close()
    except WebSocketDisconnect:
        pass
    finally:
        queues[did].discard(q)

@app.get("/{path:path}")
def frontend(path: str):
    target = STATIC_DIR / path
    if target.is_file():
        return FileResponse(target)
    html = target / "index.html"
    if html.is_file():
        return FileResponse(html)
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(404, "前端文件不存在")
