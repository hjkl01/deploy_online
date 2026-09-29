import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import SessionLocal, settings
from database import init_database
from http import install_http_handlers
from models import Deployment, DeploymentStep, Log
from routers.auth import router as auth_router
from routers.deployments import router as deployment_router
from routers.projects import router as project_router
from routers.users import router as user_router

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
    job = d.get(Deployment, did)
    rows = d.query(Log).filter_by(deployment_id=did).order_by(Log.id).all()
    initial_steps = d.query(DeploymentStep).filter_by(deployment_id=did).order_by(DeploymentStep.position).all()
    d.close()
    if not job:
        await w.close(code=1008)
        return

    await w.accept()
    try:
        await w.send_json({
            "type": "connected",
            "deployment_id": did,
            "status": job.status,
            "exit_code": job.exit_code,
            "steps": [
                {"id": s.id, "name": s.name, "status": s.status, "started_at": s.started_at,
                 "finished_at": s.finished_at, "exit_code": s.exit_code, "duration_ms": s.duration_ms,
                 "error": s.error}
                for s in initial_steps
            ],
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
            await asyncio.sleep(1)
            d = SessionLocal()
            try:
                job = d.get(Deployment, did)
                step_rows = d.query(DeploymentStep).filter_by(deployment_id=did).order_by(DeploymentStep.position).all()
                new = d.query(Log).filter(Log.deployment_id == did, Log.id > last_log).order_by(Log.id).all()
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
                        "steps": [
                            {"id": s.id, "name": s.name, "status": s.status, "started_at": s.started_at,
                             "finished_at": s.finished_at, "exit_code": s.exit_code,
                             "duration_ms": s.duration_ms, "error": s.error}
                            for s in step_rows
                        ],
                    })
                    if job.status in ("success", "failed", "cancelled"):
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
