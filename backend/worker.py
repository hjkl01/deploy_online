import asyncio
import logging

from config import settings
from database import ensure_schema
from services.deployment import run
from services.worker_state import claim_pending, recover_stale

POLL_SECONDS = 1.0
ACTIVE_POLL_SECONDS = 0.2
MAX_CONCURRENCY = max(1, settings.worker_concurrency)

logger = logging.getLogger(__name__)


async def worker():
    ensure_schema()
    recover_stale()

    active = set()
    tasks = {}

    async def reap_done():
        for project_id, task in list(tasks.items()):
            if not task.done():
                continue

            active.discard(project_id)
            tasks.pop(project_id, None)
            try:
                task.result()
            except Exception:
                logger.exception("部署任务异常退出: project_id=%s", project_id)

    while True:
        await reap_done()

        capacity = MAX_CONCURRENCY - len(tasks)
        if capacity > 0:
            candidates = claim_pending(active, capacity)
            for job_id, project_id in candidates:
                tasks[project_id] = asyncio.create_task(run(job_id))

        await asyncio.sleep(ACTIVE_POLL_SECONDS if tasks else POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(worker())
