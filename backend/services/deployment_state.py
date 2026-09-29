from config import SessionLocal, now
from models import Deployment, DeploymentStep


def is_running(deployment_id):
    d = SessionLocal()
    try:
        job = d.get(Deployment, deployment_id)
        return bool(job and job.status == "running")
    finally:
        d.close()


def is_cancel_requested(deployment_id):
    d = SessionLocal()
    try:
        job = d.get(Deployment, deployment_id)
        return bool(job and job.cancel_requested)
    finally:
        d.close()


def cancel_pending_steps(deployment_id):
    d = SessionLocal()
    try:
        finished_at = now()
        steps = d.query(DeploymentStep).filter_by(
            deployment_id=deployment_id, status="pending"
        ).all()
        for step in steps:
            step.status = "cancelled"
            step.finished_at = finished_at
            step.exit_code = 130
            step.error = "部署取消"
        d.commit()
    finally:
        d.close()


def mark_step_running(deployment_id, source_step_id):
    d = SessionLocal()
    try:
        step = d.query(DeploymentStep).filter_by(
            deployment_id=deployment_id, source_step_id=source_step_id
        ).first()
        if step:
            step.status = "running"
            step.started_at = now()
        d.commit()
    finally:
        d.close()


def mark_step_finished(deployment_id, source_step_id, code, cancelled=False):
    d = SessionLocal()
    try:
        step = d.query(DeploymentStep).filter_by(
            deployment_id=deployment_id, source_step_id=source_step_id
        ).first()
        if not step:
            return
        step.status = "cancelled" if cancelled else ("success" if code == 0 else "failed")
        step.exit_code = code
        step.finished_at = now()
        if step.started_at:
            step.duration_ms = max(
                0, int((step.finished_at - step.started_at).total_seconds() * 1000)
            )
        if code != 0:
            step.error = f"exit={code}"
        d.commit()
    finally:
        d.close()


def update_git_sha(deployment_id, before_sha=None, after_sha=None):
    d = SessionLocal()
    try:
        job = d.get(Deployment, deployment_id)
        if not job:
            return
        if before_sha is not None:
            job.before_sha = before_sha
        if after_sha is not None:
            job.after_sha = after_sha
        d.commit()
    finally:
        d.close()
