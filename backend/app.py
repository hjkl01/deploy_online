import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import SessionLocal, settings
from database import init_database
from http_handlers import install_http_handlers
from models import Deployment, DeploymentStep, Log, User
from routers.auth import router as auth_router
from routers.deployments import router as deployment_router
from routers.projects import router as project_router
from routers.users import router as user_router
from services.permissions import require_project_view_access

init_database()

app = FastAPI(title="deploy_online")
install_http_handlers(app)
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

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(project_router)
app.include_router(deployment_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/deployments/{did}")
async def ws(w: WebSocket, did: int):
    if not w.scope.get("session", {}).get("user_id"):
        await w.close(code=1008)
        return

    d = SessionLocal()
    try:
        user_id = w.scope.get("session", {}).get("user_id")
        current_user = d.get(User, user_id) if user_id else None
        job = d.get(Deployment, did)
        rows = d.query(Log).filter_by(deployment_id=did).order_by(Log.id).all()
        initial_steps = (
            d.query(DeploymentStep)
            .filter_by(deployment_id=did)
            .order_by(DeploymentStep.position)
            .all()
        )
    finally:
        d.close()

    if not job:
        await w.close(code=1008)
        return
    if not current_user or (current_user.role == "operator" and not d.query(__import__("models").ProjectMember.id).filter_by(project_id=job.project_id, user_id=current_user.id).first()):
        await w.close(code=1008)
        return

    terminal_statuses = {"success", "failed", "cancelled"}

    def step_payload(steps):
        return [
            {
                "id": s.id,
                "name": s.name,
                "status": s.status,
                "started_at": s.started_at,
                "finished_at": s.finished_at,
                "exit_code": s.exit_code,
                "duration_ms": s.duration_ms,
                "error": s.error,
            }
            for s in steps
        ]

    await w.accept()
    try:
        last_state_version = job.state_version
        last_log = rows[-1].id if rows else 0

        await w.send_json({
            "type": "connected",
            "deployment_id": did,
            "status": job.status,
            "exit_code": job.exit_code,
            "steps": step_payload(initial_steps),
        })
        await w.send_json({
            "type": "snapshot",
            "logs": [
                {"id": x.id, "step_id": x.step_id, "stream": x.stream, "message": x.message}
                for x in rows
            ],
        })

        if job.status in terminal_statuses:
            return

        last_status = job.status
        last_exit_code = job.exit_code

        while True:
            await asyncio.sleep(1)
            d = SessionLocal()
            try:
                job = d.get(Deployment, did)
                if not job:
                    break

                new = (
                    d.query(Log)
                    .filter(Log.deployment_id == did, Log.id > last_log)
                    .order_by(Log.id)
                    .all()
                )
                if new:
                    last_log = new[-1].id

                for x in new:
                    await w.send_json({
                        "type": "log",
                        "id": x.id,
                        "step_id": x.step_id,
                        "stream": x.stream,
                        "message": x.message,
                    })

                status_changed = (
                    job.status != last_status or job.exit_code != last_exit_code
                )
                steps_changed = job.state_version != last_state_version

                if status_changed or steps_changed:
                    message = {
                        "type": "status",
                        "status": job.status,
                        "exit_code": job.exit_code,
                    }

                    if steps_changed:
                        step_rows = (
                            d.query(DeploymentStep)
                            .filter_by(deployment_id=did)
                            .order_by(DeploymentStep.position)
                            .all()
                        )
                        message["steps"] = step_payload(step_rows)
                        last_state_version = job.state_version

                    await w.send_json(message)
                    last_status = job.status
                    last_exit_code = job.exit_code

                if job.status in terminal_statuses:
                    break
            finally:
                d.close()
    except WebSocketDisconnect:
        pass



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
