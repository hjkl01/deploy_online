import asyncio
from collections import defaultdict

from config import SessionLocal, now
from models import Deployment, Log

class LogBroker:
    def __init__(self, batch_size=20):
        self.batch_size = batch_size
        self.buffers = defaultdict(list)
        self.locks = defaultdict(asyncio.Lock)

    async def emit(self, deployment_id, stream, message, step_id=None, queues=None):
        async with self.locks[deployment_id]:
            self.buffers[deployment_id].append((step_id, stream, message))
            if len(self.buffers[deployment_id]) >= self.batch_size:
                await self.flush(deployment_id)

    async def flush(self, deployment_id, queues=None):
        rows = self.buffers.get(deployment_id)
        if not rows:
            return
        d = SessionLocal()
        try:
            objects = [
                Log(deployment_id=deployment_id, step_id=step_id, stream=stream, message=message)
                for step_id, stream, message in rows
            ]
            d.add_all(objects)
            d.commit()
            ids = [x.id for x in objects]
        except Exception:
            d.rollback()
            raise
        finally:
            d.close()

        self.buffers[deployment_id].clear()

    async def finish(self, deployment_id, status, code, queues=None):
        async with self.locks[deployment_id]:
            await self.flush(deployment_id)

        d = SessionLocal()
        try:
            job = d.get(Deployment, deployment_id)
            if not job:
                return
            job.status = status
            job.exit_code = code
            job.finished_at = now()
            d.commit()
        finally:
            d.close()


broker = LogBroker()
