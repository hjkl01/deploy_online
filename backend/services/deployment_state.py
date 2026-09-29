from sqlalchemy import update

from config import SessionLocal, now
from models import Deployment, DeploymentStep


def is_running(deployment_id):
    d = SessionLocal()
    try:
        status = d.query(Deployment.status).filter(Deployment.id == deployment_id).scalar()
        return status == "running"
    finally:
        d.close()


def is_cancel_requested(deployment_id):
    d = SessionLocal()
    try:
        requested = d.query(Deployment.cancel_requested).filter(
            Deployment.id == deployment_id
        ).scalar()
        return bool(requested)
    finally:
        d.close()


def cancel_pending_steps(deployment_id):
    d = SessionLocal()
    try:
        d.execute(
            update(DeploymentStep)
            .where(
                DeploymentStep.deployment_id == deployment_id,
                DeploymentStep.status == "pending",
            )
            .values(
                status="cancelled",
                finished_at=now(),
                exit_code=130,
                error="部署取消",
            )
        )
        d.execute(
            update(Deployment)
            .where(Deployment.id == deployment_id)
            .values(state_version=Deployment.state_version + 1)
        )
        d.commit()
    except Exception:
        d.rollback()
        raise
    finally:
        d.close()


def mark_step_running(deployment_id, source_step_id):
    d = SessionLocal()
    try:
        d.execute(
            update(DeploymentStep)
            .where(
                DeploymentStep.deployment_id == deployment_id,
                DeploymentStep.source_step_id == source_step_id,
            )
            .values(
                status="running",
                started_at=now(),
            )
        )
        d.execute(
            update(Deployment)
            .where(Deployment.id == deployment_id)
            .values(state_version=Deployment.state_version + 1)
        )
        d.commit()
    except Exception:
        d.rollback()
        raise
    finally:
        d.close()


def mark_step_finished(deployment_id, source_step_id, code, cancelled=False):
    d = SessionLocal()
    try:
        started_at = d.query(DeploymentStep.started_at).filter(
            DeploymentStep.deployment_id == deployment_id,
            DeploymentStep.source_step_id == source_step_id,
        ).scalar()
        if started_at is None:
            return

        finished_at = now()
        status = "cancelled" if cancelled else ("success" if code == 0 else "failed")
        values = {
            "status": status,
            "exit_code": code,
            "finished_at": finished_at,
            "duration_ms": max(
                0, int((finished_at - started_at).total_seconds() * 1000)
            ),
        }
        if code != 0:
            values["error"] = f"exit={code}"

        d.execute(
            update(DeploymentStep)
            .where(
                DeploymentStep.deployment_id == deployment_id,
                DeploymentStep.source_step_id == source_step_id,
            )
            .values(**values)
        )
        d.execute(
            update(Deployment)
            .where(Deployment.id == deployment_id)
            .values(state_version=Deployment.state_version + 1)
        )
        d.commit()
    except Exception:
        d.rollback()
        raise
    finally:
        d.close()


def update_git_sha(deployment_id, before_sha=None, after_sha=None):
    if before_sha is None and after_sha is None:
        return

    values = {}
    if before_sha is not None:
        values["before_sha"] = before_sha
    if after_sha is not None:
        values["after_sha"] = after_sha

    d = SessionLocal()
    try:
        d.execute(
            update(Deployment)
            .where(Deployment.id == deployment_id)
            .values(**values)
        )
        d.commit()
    except Exception:
        d.rollback()
        raise
    finally:
        d.close()
