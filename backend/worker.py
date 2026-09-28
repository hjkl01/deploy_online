import asyncio
from datetime import datetime, timezone

from config import SessionLocal, settings
from database import ensure_schema
from models import Deployment
from services.deployment import run

POLL_SECONDS = 1.0
MAX_CONCURRENCY = max(1, settings.worker_concurrency)

def recover_stale():
    d = SessionLocal()
    try:
        rows = d.query(Deployment).filter(Deployment.status == "running").all()
        for job in rows:
            job.status = "failed"
            job.exit_code = 125
            job.finished_at = datetime.now(timezone.utc)
            job.note = (job.note or "") + "\nWorker 重启，原部署任务未完成，已标记为失败。"
        d.commit()
    finally:
        d.close()

async def worker():
    ensure_schema()
    recover_stale()
    active = set()
    tasks = {}

    async def reap_done():
        for project_id, task in list(tasks.items()):
            if task.done():
                active.discard(project_id)
                tasks.pop(project_id, None)
                try:
                    task.result()
                except Exception:
                    pass

    while True:
        await reap_done()
        capacity = MAX_CONCURRENCY - len(tasks)
        if capacity > 0:
            d = SessionLocal()
            try:
                pending = (
                    d.query(Deployment)
                    .filter(Deployment.status == "pending")
                    .order_by(Deployment.id)
                    .limit(MAX_CONCURRENCY * 2)
                    .all()
                )
                candidates = []
                for job in pending:
                    if job.project_id not in active:
                        candidates.append((job.id, job.project_id))
                        active.add(job.project_id)
                    if len(candidates) >= capacity:
                        break
            finally:
                d.close()

            for job_id, project_id in candidates:
                tasks[project_id] = asyncio.create_task(run(job_id))

        if not tasks:
            await asyncio.sleep(POLL_SECONDS)
        else:
            await asyncio.sleep(0.2)

if __name__ == "__main__":
    asyncio.run(worker())
