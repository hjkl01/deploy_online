import asyncio
import json
import os
from collections import defaultdict
from pathlib import Path

from config import SessionLocal
from models import Deployment, Project
from security import decrypt_secret
from runtime import queues
from .deployment_state import (
    cancel_pending_steps,
    is_cancel_requested,
    is_running,
    mark_step_finished,
    mark_step_running,
    update_git_sha,
)
from .execution import execute_step
from .logging import broker

project_locks = defaultdict(asyncio.Lock)


def snapshot_project(project):
    return json.dumps(
        {
            "project": {
                "name": project.name,
                "branch": project.branch,
                "shell": project.shell,
                "enabled": project.enabled,
            },
            "steps": [
                {
                    "id": step.id,
                    "name": step.name,
                    "type": step.step_type,
                    "cwd": step.cwd,
                    "command": step.command,
                    "enabled": step.enabled,
                    "timeout": step.timeout,
                    "continue_on_error": step.continue_on_error,
                    "position": step.position,
                }
                for step in project.steps
            ],
            "environment": [
                {"key": env.key, "value": env.value, "is_secret": env.is_secret}
                for env in project.envs
            ],
        },
        ensure_ascii=False,
    )


def _load_deployment(deployment_id):
    d = SessionLocal()
    try:
        job = d.get(Deployment, deployment_id)
        if not job:
            return None, None, None
        project = d.get(Project, job.project_id)
        if not project:
            return job, None, None
        snapshot = (
            json.loads(job.config_snapshot)
            if job.config_snapshot
            else json.loads(snapshot_project(project))
        )
        return job, project, snapshot
    finally:
        d.close()


def _build_environment(snapshot):
    env = os.environ.copy()
    env.update(
        {
            item["key"]: decrypt_secret(item["value"]) if item["is_secret"] else item["value"]
            for item in snapshot["environment"]
        }
    )
    return env


async def run(deployment_id):
    job, project, snapshot = _load_deployment(deployment_id)
    if not job:
        return
    if not project:
        await broker.emit(
            deployment_id, "stderr", "项目不存在，部署终止\n", None, queues
        )
        await broker.finish(deployment_id, "failed", 1, queues)
        return

    project_id = project.id
    async with project_locks[project_id]:
        if not is_running(deployment_id):
            return

        env = _build_environment(snapshot)
        project_cfg = snapshot["project"]
        cancelled = False
        success = True
        exit_code = 0
        before_sha = None
        after_sha = None

        try:
            await broker.emit(
                deployment_id,
                "system",
                f'开始部署 {project_cfg["name"]}\nShell: {project_cfg["shell"]}\n',
                None,
                queues,
            )

            for step in snapshot["steps"]:
                if not step["enabled"]:
                    continue

                if is_cancel_requested(deployment_id):
                    cancelled = True
                    cancel_pending_steps(deployment_id)
                    break

                step_id = step.get("id")
                mark_step_running(deployment_id, step_id)

                if step["type"] == "git_pull":
                    before_sha = await _git_sha(step["cwd"])
                    if before_sha:
                        update_git_sha(deployment_id, before_sha=before_sha)

                code, was_cancelled, step_after_sha = await execute_step(
                    deployment_id,
                    project_cfg,
                    env,
                    step,
                    lambda: asyncio.to_thread(is_cancel_requested, deployment_id),
                )

                if step_after_sha:
                    after_sha = step_after_sha

                mark_step_finished(
                    deployment_id,
                    step_id,
                    code,
                    cancelled=was_cancelled,
                )

                if code != 0:
                    success = False
                    exit_code = code
                    await broker.emit(
                        deployment_id,
                        "system",
                        f'[{step["name"]}] 失败 exit={code}\n',
                        step_id,
                        queues,
                    )
                    if was_cancelled or not step["continue_on_error"]:
                        cancelled = was_cancelled
                        break
                else:
                    await broker.emit(
                        deployment_id,
                        "system",
                        f'[{step["name"]}] 完成\n',
                        step_id,
                        queues,
                    )

            if before_sha or after_sha:
                update_git_sha(
                    deployment_id,
                    before_sha=before_sha,
                    after_sha=after_sha,
                )

            if cancelled or is_cancel_requested(deployment_id):
                await broker.emit(
                    deployment_id, "system", "\n部署已取消\n", None, queues
                )
                await broker.finish(deployment_id, "cancelled", 130, queues)
            else:
                status = "success" if success else "failed"
                await broker.emit(
                    deployment_id,
                    "system",
                    f'\n部署{"成功" if success else "失败"}\n',
                    None,
                    queues,
                )
                await broker.finish(deployment_id, status, exit_code, queues)
        except asyncio.CancelledError:
            await broker.emit(
                deployment_id, "stderr", "部署任务被 Worker 取消\n", None, queues
            )
            await broker.finish(deployment_id, "failed", 130, queues)
            raise
        except Exception as exc:
            await broker.emit(
                deployment_id, "stderr", f"部署任务异常: {exc}\n", None, queues
            )
            await broker.finish(deployment_id, "failed", 1, queues)


async def _git_sha(cwd):
    from .executor import git_sha

    return await git_sha(Path(cwd).expanduser().resolve())
