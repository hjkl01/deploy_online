import asyncio
import shlex
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .executor import git_sha, kill_process_group, shell_command
from .logging import broker
from runtime import queues

ALLOWED_STEP_TYPES = {"command", "git_pull", "restart", "health_check"}


def _health_check(url, timeout):
    request = Request(url, method="GET", headers={"User-Agent": "deploy_online-health-check"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.reason or ""
    except HTTPError as exc:
        return exc.code, exc.reason or ""
    except URLError as exc:
        raise RuntimeError(f"health check 请求失败: {exc.reason}") from exc


async def execute_step(deployment_id, project_cfg, env, step, cancel_checker):
    step_id = step.get("id")
    name = step["name"]
    step_type = step["type"]
    cwd = Path(step["cwd"]).expanduser().resolve()

    if step_type not in ALLOWED_STEP_TYPES:
        await broker.emit(deployment_id, "stderr", f"[{name}] 未知步骤类型: {step_type}\n", step_id, queues)
        return 1, False, None

    if step_type == "health_check":
        url = step["command"].strip()
        if not url.startswith(("http://", "https://")):
            await broker.emit(deployment_id, "stderr", f"[{name}] health_check URL 无效: {url}\n", step_id, queues)
            return 1, False, None
        try:
            status, reason = await asyncio.to_thread(
                _health_check, url, max(1, int(step.get("timeout") or 30))
            )
            await broker.emit(
                deployment_id, "system", f"[{name}] HTTP {status} {reason}\n", step_id, queues
            )
            return (0 if 200 <= status < 300 else status), False, None
        except Exception as exc:
            await broker.emit(deployment_id, "stderr", f"[{name}] {exc}\n", step_id, queues)
            return 1, False, None

    command = (
        "git checkout " + shlex.quote(project_cfg["branch"]) + " && git pull --ff-only"
        if step_type == "git_pull"
        else step["command"]
    )

    if not cwd.is_dir():
        await broker.emit(deployment_id, "stderr", f"[{name}] cwd 不存在: {cwd}\n", step_id, queues)
        return 1, False, None

    if not command.strip():
        await broker.emit(deployment_id, "system", f"[{name}] 无命令，跳过\n", step_id, queues)
        return 0, False, None

    await broker.emit(
        deployment_id, "system", f"\n>>> {name}\n$ {command}\n", step_id, queues
    )
    proc = await asyncio.create_subprocess_exec(
        *shell_command(project_cfg["shell"], command),
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    async def read_stream(stream, stream_name):
        while line := await stream.readline():
            await broker.emit(
                deployment_id, stream_name, line.decode(errors="replace"), step_id, queues
            )

    async def watch_cancel():
        while proc.returncode is None:
            await asyncio.sleep(0.5)
            if await cancel_checker():
                kill_process_group(proc)
                return True
        return False

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
        was_cancelled = watcher.done() and watcher.result()
        code = 130 if was_cancelled else proc.returncode
    except asyncio.TimeoutError:
        kill_process_group(proc)
        await proc.wait()
        code = 124
        was_cancelled = False
        await broker.emit(deployment_id, "stderr", f"[{name}] 超时\n", step_id, queues)
    except Exception as exc:
        kill_process_group(proc)
        await proc.wait()
        code = 1
        was_cancelled = False
        await broker.emit(deployment_id, "stderr", f"[{name}] {exc}\n", step_id, queues)
    finally:
        watcher.cancel()

    if step_type == "git_pull" and code == 0:
        return code, False, await git_sha(cwd)
    return code, code == 130 or was_cancelled, None
