import asyncio
import logging
import signal

from config import settings
from database import ensure_schema
from services.deployment import run
from services.worker_state import claim_pending, recover_stale

POLL_SECONDS = 1.0
ACTIVE_POLL_SECONDS = 0.2
SHUTDOWN_TIMEOUT = 30.0
MAX_CONCURRENCY = max(1, settings.worker_concurrency)

logger = logging.getLogger(__name__)


async def worker():
    ensure_schema()
    recover_stale()

    active = set()
    tasks = {}
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown():
        if not shutdown.is_set():
            logger.info("收到停止信号，Worker 将停止领取新部署任务")
            shutdown.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, request_shutdown)
        except (NotImplementedError, RuntimeError):
            pass

    async def reap_done():
        for project_id, task in list(tasks.items()):
            if not task.done():
                continue

            active.discard(project_id)
            tasks.pop(project_id, None)
            try:
                task.result()
            except asyncio.CancelledError:
                logger.info("部署任务被 Worker 取消: project_id=%s", project_id)
            except Exception:
                logger.exception("部署任务异常退出: project_id=%s", project_id)

    try:
        while not shutdown.is_set():
            await reap_done()

            capacity = MAX_CONCURRENCY - len(tasks)
            if capacity > 0:
                candidates = claim_pending(active, capacity)
                for job_id, project_id in candidates:
                    tasks[project_id] = asyncio.create_task(run(job_id))

            try:
                await asyncio.wait_for(
                    shutdown.wait(),
                    timeout=ACTIVE_POLL_SECONDS if tasks else POLL_SECONDS,
                )
            except asyncio.TimeoutError:
                pass

        logger.info("停止领取新任务，等待当前部署完成: %d", len(tasks))
        if tasks:
            done, pending = await asyncio.wait(
                list(tasks.values()),
                timeout=SHUTDOWN_TIMEOUT,
            )
            for task in pending:
                logger.warning("部署任务超过退出等待时间，将取消")
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("部署任务退出时异常")

    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.remove_signal_handler(signum)
            except (NotImplementedError, RuntimeError):
                pass


if __name__ == "__main__":
    asyncio.run(worker())
