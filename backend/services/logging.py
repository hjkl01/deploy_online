import asyncio
from collections import defaultdict

from config import SessionLocal, now
from models import Deployment, Log


class LogBroker:
    def __init__(self, batch_size=20, flush_interval=1.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buffers = defaultdict(list)
        self.locks = defaultdict(asyncio.Lock)
        self.flush_tasks = {}

    async def emit(self, deployment_id, stream, message, step_id=None, queues=None):
        async with self.locks[deployment_id]:
            buffer = self.buffers[deployment_id]
            buffer.append((step_id, stream, message))

            if len(buffer) >= self.batch_size:
                await self.flush(deployment_id)
                self._cancel_flush_task(deployment_id)
            elif deployment_id not in self.flush_tasks:
                self.flush_tasks[deployment_id] = asyncio.create_task(
                    self._delayed_flush(deployment_id)
                )

    async def _delayed_flush(self, deployment_id):
        try:
            await asyncio.sleep(self.flush_interval)
            async with self.locks[deployment_id]:
                await self.flush(deployment_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # 保留 buffer，下一次 emit 或 finish 会再次尝试刷盘。
            return
        finally:
            current = asyncio.current_task()
            if self.flush_tasks.get(deployment_id) is current:
                self.flush_tasks.pop(deployment_id, None)

    def _cancel_flush_task(self, deployment_id):
        task = self.flush_tasks.pop(deployment_id, None)
        if task and task is not asyncio.current_task():
            task.cancel()

    async def flush(self, deployment_id, queues=None):
        rows = self.buffers.get(deployment_id)
        if not rows:
            return

        # 复制当前批次，只有数据库提交成功后才从内存 buffer 删除。
        batch = list(rows)
        d = SessionLocal()
        try:
            objects = [
                Log(
                    deployment_id=deployment_id,
                    step_id=step_id,
                    stream=stream,
                    message=message,
                )
                for step_id, stream, message in batch
            ]
            d.add_all(objects)
            d.commit()
        except Exception:
            d.rollback()
            raise
        finally:
            d.close()

        del rows[:len(batch)]

    async def finish(self, deployment_id, status, code, queues=None):
        flush_task = self.flush_tasks.get(deployment_id)
        if flush_task and flush_task is not asyncio.current_task():
            flush_task.cancel()

        async with self.locks[deployment_id]:
            await self.flush(deployment_id)

            d = SessionLocal()
            try:
                job = d.get(Deployment, deployment_id)
                if job:
                    job.status = status
                    job.exit_code = code
                    job.finished_at = now()
                    d.commit()
            except Exception:
                d.rollback()
                raise
            except Exception:
                d.rollback()
                raise
            finally:
                d.close()

        self._cancel_flush_task(deployment_id)
        self.buffers.pop(deployment_id, None)
        self.locks.pop(deployment_id, None)


broker = LogBroker()
