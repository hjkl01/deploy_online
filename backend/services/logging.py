import asyncio
from collections import defaultdict
from config import SessionLocal
from models import Log

class LogBroker:
    def __init__(self, batch_size=20):
        self.batch_size = batch_size
        self.buffers = defaultdict(list)
        self.locks = defaultdict(asyncio.Lock)

    async def emit(self, deployment_id, stream, message, step_id=None, queues=None):
        async with self.locks[deployment_id]:
            self.buffers[deployment_id].append((step_id, stream, message))
            if len(self.buffers[deployment_id]) >= self.batch_size:
                await self.flush(deployment_id, queues)

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
        finally:
            d.close()
            self.buffers[deployment_id].clear()

        if queues is not None:
            for index, (step_id, stream, message) in enumerate(rows):
                payload = {
                    "type": "log",
                    "id": ids[index],
                    "step_id": step_id,
                    "stream": stream,
                    "message": message,
                }
                for q in list(queues[deployment_id]):
                    await q.put(payload)

    async def finish(self, deployment_id, status, code, queues=None):
        async with self.locks[deployment_id]:
            await self.flush(deployment_id, queues)
        d = SessionLocal()
        try:
            from config import now
            job = d.get(__import__("models").Deployment, deployment_id)
            if not job:
                return
            job.status = status
            job.exit_code = code
            job.finished_at = now()
            d.commit()
        finally:
            d.close()
        if queues is not None:
            payload = {"type": "status", "status": status, "exit_code": code}
            for q in list(queues[deployment_id]):
                await q.put(payload)

broker = LogBroker()
