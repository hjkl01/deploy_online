from sqlalchemy import update

from config import SessionLocal, now
from models import Deployment, DeploymentStep


def recover_stale():
    """恢复 Worker 重启时遗留的 running 部署和步骤。"""
    d = SessionLocal()
    try:
        finished_at = now()
        rows = d.query(Deployment).filter(Deployment.status == "running").all()
        for job in rows:
            job.status = "failed"
            job.exit_code = 125
            job.finished_at = finished_at
            job.note = (job.note or "") + "\nWorker 重启，原部署任务未完成，已标记为失败。"

            steps = d.query(DeploymentStep).filter_by(
                deployment_id=job.id,
                status="running",
            ).all()
            for step in steps:
                step.status = "failed"
                step.exit_code = 125
                step.finished_at = finished_at
                step.error = "Worker 重启，任务中断"

        d.commit()
    finally:
        d.close()


def claim_pending(active_project_ids, capacity):
    """原子领取 pending 部署，并保证当前 Worker 内同一项目串行执行。"""
    if capacity <= 0:
        return []

    d = SessionLocal()
    try:
        query = d.query(Deployment).filter(Deployment.status == "pending")
        if active_project_ids:
            query = query.filter(~Deployment.project_id.in_(active_project_ids))

        pending = query.order_by(Deployment.id).limit(capacity).all()
        candidates = []

        for job in pending:
            result = d.execute(
                update(Deployment)
                .where(
                    Deployment.id == job.id,
                    Deployment.status == "pending",
                )
                .values(
                    status="running",
                    started_at=now(),
                )
            )
            if result.rowcount == 1:
                candidates.append((job.id, job.project_id))

        if candidates:
            d.commit()

        return candidates
    except Exception:
        d.rollback()
        raise
    finally:
        d.close()
