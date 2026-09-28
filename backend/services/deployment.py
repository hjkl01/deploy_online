import asyncio
import json
import os
import shlex
from collections import defaultdict
from pathlib import Path

from config import SessionLocal, now
from models import Deployment, DeploymentStep, Project
from security import decrypt_secret
from .executor import git_sha, kill_process_group, shell_command
from .logging import broker
from runtime import queues

project_locks = defaultdict(asyncio.Lock)

def snapshot_project(project):
    return json.dumps({
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
    }, ensure_ascii=False)

async def _execute_step(deployment_id, project_cfg, env, step, cancelled):
    cwd = Path(step["cwd"]).expanduser().resolve()
    command = (
        "git checkout " + shlex.quote(project_cfg["branch"]) + " && git pull --ff-only"
        if step["type"] == "git_pull" else step["command"]
    )
    step_id = step.get("id")

    if not cwd.is_dir():
        await broker.emit(deployment_id, "stderr", f'[{step["name"]}] cwd 不存在: {cwd}\n', step_id, queues)
        return 1, False, None

    if not command.strip():
        await broker.emit(deployment_id, "system", f'[{step["name"]}] 无命令，跳过\n', step_id, queues)
        return 0, False, None

    await broker.emit(deployment_id, "system", f'\n>>> {step["name"]}\n$ {command}\n', step_id, queues)
    proc = await asyncio.create_subprocess_exec(
        *shell_command(project_cfg["shell"], command),
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    async def read_stream(stream, name):
        while line := await stream.readline():
            await broker.emit(deployment_id, name, line.decode(errors="replace"), step_id, queues)

    async def watch_cancel():
        while proc.returncode is None:
            await asyncio.sleep(0.5)
            d = SessionLocal()
            try:
                job = d.get(Deployment, deployment_id)
                if job and job.cancel_requested:
                    cancelled[0] = True
                    kill_process_group(proc)
                    return
            finally:
                d.close()

    watcher = asyncio.create_task(watch_cancel())
    try:
        await asyncio.wait_for(
            asyncio.gather(
                read_stream(proc.stdout, "stdout"),
                read_stream(proc.stderr, "stderr"),
                proc.wait(),
            ),
            timeout=max(1, int(step.get("timeout") or 3600)),
        )
        code = 130 if cancelled[0] else proc.returncode
    except asyncio.TimeoutError:
        kill_process_group(proc)
        await proc.wait()
        code = 124
        await broker.emit(deployment_id, "stderr", f'[{step["name"]}] 超时\n', step_id, queues)
    except Exception as exc:
        kill_process_group(proc)
        await proc.wait()
        code = 1
        await broker.emit(deployment_id, "stderr", f'[{step["name"]}] {exc}\n', step_id, queues)
    finally:
        watcher.cancel()

    if step["type"] == "git_pull" and code == 0:
        return code, False, await git_sha(cwd)
    return code, code == 130, None

async def run(deployment_id):
    d = SessionLocal()
    try:
        job = d.get(Deployment, deployment_id)
        if not job:
            return
        project = d.get(Project, job.project_id)
        if not project:
            await broker.emit(deployment_id, "stderr", "项目不存在，部署终止\n", None, queues)
            await broker.finish(deployment_id, "failed", 1, queues)
            return
        snapshot = json.loads(job.config_snapshot) if job.config_snapshot else json.loads(snapshot_project(project))
        project_id = project.id
    finally:
        d.close()

    async with project_locks[project_id]:
        d = SessionLocal()
        try:
            job = d.get(Deployment, deployment_id)
            if not job or job.status != "pending":
                return
            job.status = "running"
            job.started_at = now()
            d.commit()
            env_values = list(json.loads(snapshot)["environment"])
        finally:
            d.close()

        env = os.environ.copy()
        env.update({
            item["key"]: decrypt_secret(item["value"]) if item["is_secret"] else item["value"]
            for item in env_values
        })
        project_cfg = snapshot["project"]
        cancelled = [False]
        success = True
        exit_code = 0
        before_sha = None
        after_sha = None

        try:
            await broker.emit(
                deployment_id, "system",
                f'开始部署 {project_cfg["name"]}\nShell: {project_cfg["shell"]}\n',
                None, queues,
            )

            for step in snapshot["steps"]:
                d = SessionLocal()
                try:
                    job = d.get(Deployment, deployment_id)
                    if not job or job.cancel_requested:
                        cancelled[0] = True
                        break
                finally:
                    d.close()

                if not step["enabled"]:
                    continue

                d = SessionLocal()
                step_row = d.query(DeploymentStep).filter_by(deployment_id=deployment_id, source_step_id=step.get("id")).first()
                if step_row:
                    step_row.status = "running"
                    step_row.started_at = now()
                    d.commit()
                finally_d = d
                d.close()

                if step["type"] == "git_pull":
                    before_sha = await git_sha(Path(step["cwd"]).expanduser().resolve())
                    if before_sha:
                        d = SessionLocal()
                        try:
                            job = d.get(Deployment, deployment_id)
                            if job:
                                job.before_sha = before_sha
                                d.commit()
                        finally:
                            d.close()

                code, was_cancelled, step_after_sha = await _execute_step(
                    deployment_id, project_cfg, env, step, cancelled
                )
                if step_after_sha:
                    after_sha = step_after_sha

                d = SessionLocal()
                try:
                    step_row = d.query(DeploymentStep).filter_by(deployment_id=deployment_id, source_step_id=step.get("id")).first()
                    if step_row:
                        step_row.status = "cancelled" if was_cancelled else "failed"
                        step_row.exit_code = code
                        step_row.finished_at = now()
                        if step_row.started_at:
                            step_row.duration_ms = max(0, int((step_row.finished_at - step_row.started_at).total_seconds() * 1000))
                        if code != 0:
                            step_row.error = f"exit={code}"
                        d.commit()
                finally:
                    d.close()

                if code != 0:
                    success = False
                    exit_code = code
                    await broker.emit(
                        deployment_id, "system",
                        f'[{step["name"]}] 失败 exit={code}\n',
                        step.get("id"), queues,
                    )
                    if was_cancelled or not step["continue_on_error"]:
                        break
                else:
                    d = SessionLocal()
                    try:
                        step_row = d.query(DeploymentStep).filter_by(deployment_id=deployment_id, source_step_id=step.get("id")).first()
                        if step_row:
                            step_row.status = "success"
                            step_row.exit_code = 0
                            step_row.finished_at = now()
                            if step_row.started_at:
                                step_row.duration_ms = max(0, int((step_row.finished_at - step_row.started_at).total_seconds() * 1000))
                            d.commit()
                    finally:
                        d.close()
                    await broker.emit(
                        deployment_id, "system",
                        f'[{step["name"]}] 完成\n',
                        step.get("id"), queues,
                    )

            if before_sha or after_sha:
                d = SessionLocal()
                try:
                    job = d.get(Deployment, deployment_id)
                    if job:
                        job.before_sha = before_sha
                        job.after_sha = after_sha
                        d.commit()
                finally:
                    d.close()

            if cancelled[0]:
                await broker.emit(deployment_id, "system", "\n部署已取消\n", None, queues)
                await broker.finish(deployment_id, "cancelled", 130, queues)
            else:
                status = "success" if success else "failed"
                await broker.emit(
                    deployment_id, "system",
                    f'\n部署{"成功" if success else "失败"}\n',
                    None, queues,
                )
                await broker.finish(deployment_id, status, exit_code, queues)
        except asyncio.CancelledError:
            await broker.emit(deployment_id, "stderr", "部署任务被 Worker 取消\n", None, queues)
            await broker.finish(deployment_id, "failed", 130, queues)
            raise
        except Exception as exc:
            await broker.emit(deployment_id, "stderr", f"部署任务异常: {exc}\n", None, queues)
            await broker.finish(deployment_id, "failed", 1, queues)
