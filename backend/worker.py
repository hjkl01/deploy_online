import asyncio
from datetime import datetime, timezone
from config import SessionLocal
from models import Deployment
from app import run, ensure_schema

POLL_SECONDS=1.0

def recover_stale():
 d=SessionLocal()
 rows=d.query(Deployment).filter(Deployment.status=="running").all()
 for j in rows:
  j.status="failed"
  j.exit_code=125
  j.finished_at=datetime.now(timezone.utc)
  j.note=(j.note or "") + "\nWorker 重启，原部署任务未完成，已标记为失败。"
 d.commit()
 d.close()

async def worker():
 ensure_schema()
 recover_stale()
 while True:
  d=SessionLocal()
  job=d.query(Deployment).filter(Deployment.status=="pending").order_by(Deployment.id).first()
  job_id=job.id if job else None
  d.close()
  if job_id is not None:
   try:
    await run(job_id)
   except Exception:
    d=SessionLocal()
    j=d.get(Deployment,job_id)
    if j and j.status in ("pending","running"):
     j.status="failed"
     j.exit_code=1
     j.finished_at=datetime.now(timezone.utc)
     d.commit()
    d.close()
  else:
   await asyncio.sleep(POLL_SECONDS)

if __name__=="__main__":
 asyncio.run(worker())
