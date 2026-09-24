import asyncio,os,shlex,signal
from datetime import datetime,timezone
from pathlib import Path
from collections import defaultdict
import yaml
from fastapi import FastAPI,Depends,HTTPException,Request,WebSocket,WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel,Field
from pydantic_settings import BaseSettings
import bcrypt
from sqlalchemy import create_engine,Column,Integer,String,Text,Boolean,ForeignKey,DateTime
from sqlalchemy.orm import declarative_base,sessionmaker,Session,relationship

class Settings(BaseSettings):
 model_config={"env_file":".env","env_file_encoding":"utf-8","extra":"ignore"}
 database_url:str="sqlite:///./data/deploy_online.db";secret_key:str="change-me";admin_username:str="admin";admin_password:str="admin"
settings=Settings();Path("data").mkdir(exist_ok=True)
engine=create_engine(settings.database_url,connect_args={"check_same_thread":False});SessionLocal=sessionmaker(bind=engine,expire_on_commit=False);Base=declarative_base();now=lambda:datetime.now(timezone.utc)
class User(Base):
 __tablename__="users";id=Column(Integer,primary_key=True);username=Column(String(100),unique=True);password_hash=Column(String(255));role=Column(String(20),default="viewer")
class Project(Base):
 __tablename__="projects";id=Column(Integer,primary_key=True);name=Column(String(200));description=Column(Text,default="");branch=Column(String(255),default="main");shell=Column(String(20),default="bash");enabled=Column(Boolean,default=True)
 steps=relationship("Step",cascade="all,delete-orphan",order_by="Step.position");envs=relationship("Env",cascade="all,delete-orphan")
class Step(Base):
 __tablename__="steps";id=Column(Integer,primary_key=True);project_id=Column(ForeignKey("projects.id"));name=Column(String(200));step_type=Column(String(30),default="command");cwd=Column(String(1000),default="~");command=Column(Text,default="");enabled=Column(Boolean,default=True);timeout=Column(Integer,default=3600);continue_on_error=Column(Boolean,default=False);position=Column(Integer,default=0)
class Env(Base):
 __tablename__="envs";id=Column(Integer,primary_key=True);project_id=Column(ForeignKey("projects.id"));key=Column(String(255));value=Column(Text,default="");is_secret=Column(Boolean,default=False)
class Deployment(Base):
 __tablename__="deployments";id=Column(Integer,primary_key=True);project_id=Column(Integer);user_id=Column(Integer);status=Column(String(30),default="pending");exit_code=Column(Integer);created_at=Column(DateTime,default=now);started_at=Column(DateTime);finished_at=Column(DateTime)
class Log(Base):
 __tablename__="logs";id=Column(Integer,primary_key=True);deployment_id=Column(Integer,index=True);stream=Column(String(20));message=Column(Text);created_at=Column(DateTime,default=now)
db_path=Path(settings.database_url.replace("sqlite:///","")).expanduser()
if not db_path.is_absolute():db_path=Path(__file__).resolve().parent/db_path
db_path.parent.mkdir(parents=True,exist_ok=True)
Base.metadata.create_all(engine)
def hash_password(password:str):
 if len(password.encode()) > 72:
  raise RuntimeError("ADMIN_PASSWORD 不能超过 72 字节")
 return bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
def verify_password(password:str,password_hash:str):
 try:return bcrypt.checkpw(password.encode(),password_hash.encode())
 except (ValueError,TypeError):return False
d=SessionLocal()
if not d.query(User).first():
 d.add(User(username=settings.admin_username,password_hash=hash_password(settings.admin_password),role="admin"))
 d.commit()
d.close()
class Login(BaseModel):username:str;password:str
class StepIn(BaseModel):
 name:str;step_type:str="command";cwd:str="~";command:str="";enabled:bool=True;timeout:int=Field(3600,ge=1,le=86400);continue_on_error:bool=False
class EnvIn(BaseModel):key:str;value:str="";is_secret:bool=False
class ProjectIn(BaseModel):
 name:str;description:str="";branch:str="main";shell:str="bash";enabled:bool=True;steps:list[StepIn]=Field(default_factory=list);environment:list[EnvIn]=Field(default_factory=list)
class UserIn(BaseModel):
 username:str
 password:str=""
 role:str="viewer"
app=FastAPI(title="deploy_online");
STATIC_DIR=Path(__file__).resolve().parent/"static"
if (STATIC_DIR/"_next").is_dir(): app.mount("/_next",StaticFiles(directory=STATIC_DIR/"_next"),name="next")
app.add_middleware(SessionMiddleware,secret_key=settings.secret_key)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000","http://127.0.0.1:3000"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
locks=defaultdict(asyncio.Lock);queues=defaultdict(set)
def dbdep():
 d=SessionLocal()
 try:yield d
 finally:d.close()
def user(request:Request,d:Session=Depends(dbdep)):
 u=d.get(User,request.session.get("user_id")) if request.session.get("user_id") else None
 if not u:raise HTTPException(401,"未登录")
 return u
def role(*roles):
 def dep(u=Depends(user)):
  if u.role not in roles:raise HTTPException(403,"没有权限")
  return u
 return dep
def check(x):
 if x.shell not in ("bash","zsh"):raise HTTPException(400,"shell 只能是 bash 或 zsh")
 home=Path.home().resolve()
 for s in x.steps:
  if s.cwd != "~" and not s.cwd.startswith("~/"):raise HTTPException(400,"cwd 必须从用户家目录 ~ 开始")
  relative="" if s.cwd == "~" else s.cwd[2:]
  target=(home / relative).resolve()
  if target != home and home not in target.parents:raise HTTPException(400,"cwd 不能越出用户家目录")
 for e in x.environment:
  if not e.key or "=" in e.key or "\x00" in e.key:raise HTTPException(400,"环境变量名无效")
def po(p):return {"id":p.id,"name":p.name,"description":p.description,"branch":p.branch,"shell":p.shell,"enabled":p.enabled}
@app.get("/health")
def health():return {"status":"ok"}
@app.post("/api/auth/login")
def login(x:Login,request:Request,d:Session=Depends(dbdep)):
 u=d.query(User).filter_by(username=x.username).first()
 if not u or not verify_password(x.password,u.password_hash):raise HTTPException(401,"用户名或密码错误")
 request.session["user_id"]=u.id;return {"id":u.id,"username":u.username,"role":u.role}
@app.post("/api/auth/logout")
def logout(request:Request):request.session.clear();return {"ok":True}
@app.get("/api/auth/me")
def me(u=Depends(user)):return {"id":u.id,"username":u.username,"role":u.role}
@app.get("/api/users")
def users(d:Session=Depends(dbdep),u=Depends(role("admin"))):
 return [{"id":x.id,"username":x.username,"role":x.role} for x in d.query(User).order_by(User.id).all()]

@app.post("/api/users")
def create_user(x:UserIn,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 if not x.username.strip() or not x.password: raise HTTPException(400,"用户名和密码不能为空")
 if x.role not in ("admin","operator","viewer"): raise HTTPException(400,"角色无效")
 if len(x.password.encode())>72: raise HTTPException(400,"密码不能超过 72 字节")
 if d.query(User).filter_by(username=x.username.strip()).first(): raise HTTPException(409,"用户名已存在")
 v=User(username=x.username.strip(),password_hash=hash_password(x.password),role=x.role);d.add(v);d.commit();d.refresh(v)
 return {"id":v.id,"username":v.username,"role":v.role}

@app.put("/api/users/{uid}")
def update_user(uid:int,x:UserIn,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 v=d.get(User,uid)
 if not v: raise HTTPException(404,"用户不存在")
 if x.role not in ("admin","operator","viewer"): raise HTTPException(400,"角色无效")
 other=d.query(User).filter(User.username==x.username.strip(),User.id!=uid).first()
 if other: raise HTTPException(409,"用户名已存在")
 v.username=x.username.strip();v.role=x.role
 if x.password:
  if len(x.password.encode())>72: raise HTTPException(400,"密码不能超过 72 字节")
  v.password_hash=hash_password(x.password)
 d.commit()
 return {"id":v.id,"username":v.username,"role":v.role}

@app.delete("/api/users/{uid}")
def delete_user(uid:int,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 if uid==u.id: raise HTTPException(400,"不能删除当前登录用户")
 v=d.get(User,uid)
 if not v: raise HTTPException(404,"用户不存在")
 if v.role=="admin" and d.query(User).filter_by(role="admin").count()<=1: raise HTTPException(400,"至少保留一个管理员")
 d.delete(v);d.commit();return {"ok":True}

@app.get("/api/projects")
def projects(d:Session=Depends(dbdep),u=Depends(role("admin","operator","viewer"))):return [po(p) for p in d.query(Project).order_by(Project.id.desc())]
@app.get("/api/projects/{pid}")
def project(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin","operator","viewer"))):
 p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 x=po(p);x["steps"]=[{"id":s.id,"name":s.name,"step_type":s.step_type,"cwd":s.cwd,"command":s.command,"enabled":s.enabled,"timeout":s.timeout,"continue_on_error":s.continue_on_error,"position":s.position} for s in p.steps];x["environment"]=[{"id":e.id,"key":e.key,"value":"" if e.is_secret else e.value,"is_secret":e.is_secret} for e in p.envs];return x
@app.post("/api/projects")
def create(x:ProjectIn,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 check(x);p=Project(name=x.name,description=x.description,branch=x.branch,shell=x.shell,enabled=x.enabled);d.add(p);d.flush()
 for i,s in enumerate(x.steps):d.add(Step(project_id=p.id,position=i,**s.model_dump()))
 for e in x.environment:d.add(Env(project_id=p.id,**e.model_dump()))
 d.commit();d.refresh(p);return po(p)
@app.put("/api/projects/{pid}")
def update(pid:int,x:ProjectIn,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 check(x);p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 p.name=x.name;p.description=x.description;p.branch=x.branch;p.shell=x.shell;p.enabled=x.enabled
 existing_secret={e.key:e.value for e in d.query(Env).filter_by(project_id=pid,is_secret=True).all()}
 d.query(Step).filter_by(project_id=pid).delete();d.query(Env).filter_by(project_id=pid).delete()
 for i,s in enumerate(x.steps):d.add(Step(project_id=pid,position=i,**s.model_dump()))
 for e in x.environment:
  data=e.model_dump()
  if data["is_secret"] and data["value"]=="" and data["key"] in existing_secret:
   data["value"]=existing_secret[data["key"]]
  d.add(Env(project_id=pid,**data))
 d.commit();return po(p)
@app.delete("/api/projects/{pid}")
def delete(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 d.delete(p);d.commit();return {"ok":True}
async def emit(i,stream,msg):
 d=SessionLocal();d.add(Log(deployment_id=i,stream=stream,message=msg));d.commit(); item=d.query(Log).filter_by(deployment_id=i).order_by(Log.id.desc()).first(); d.close()
 for q in list(queues[i]):await q.put({"type":"log","id":item.id,"stream":stream,"message":msg})
async def finish(i,status,code):
 d=SessionLocal();j=d.get(Deployment,i)
 if not j:d.close();return
 j.status=status;j.exit_code=code;j.finished_at=now();d.commit();d.close()
 for q in list(queues[i]):await q.put({"type":"status","status":status,"exit_code":code})
def sh(shell,cmd):return ["/bin/bash","-lic",cmd] if shell=="bash" else ["/bin/zsh","-lic",cmd]
def kill_process_group(proc):
 if not proc or proc.returncode is not None:return
 try:
  os.killpg(proc.pid,signal.SIGKILL)
 except ProcessLookupError:
  pass

async def run(i):
 d=SessionLocal();j=d.get(Deployment,i)
 if not j:d.close();return
 p=d.get(Project,j.project_id)
 if not p:
  d.close()
  await finish(i,"failed",1)
  await emit(i,"stderr","项目不存在，部署终止\n")
  return
 steps=d.query(Step).filter_by(project_id=p.id).order_by(Step.position).all();envs=d.query(Env).filter_by(project_id=p.id).all();d.close()
 async with locks[p.id]:
  d=SessionLocal();j=d.get(Deployment,i)
  if not j:d.close();return
  j.status="running";j.started_at=now();d.commit();d.close()
  env=os.environ.copy();env.update({e.key:e.value for e in envs});ok=True;code=0;finished=False
  try:
   await emit(i,"system",f"开始部署 {p.name}\nShell: {p.shell}\n")
   for s in steps:
    if not s.enabled:continue
    cwd=Path(s.cwd).expanduser().resolve();cmd=("git checkout "+shlex.quote(p.branch)+" && git pull --ff-only") if s.step_type=="git_pull" else s.command
    step_failed=False;step_code=0
    if not cwd.is_dir():
     await emit(i,"stderr",f"[{s.name}] cwd 不存在: {cwd}\n");step_failed=True;step_code=1
    elif cmd.strip():
     await emit(i,"system",f"\n>>> {s.name}\n$ {cmd}\n");proc=None
     try:
      proc=await asyncio.create_subprocess_exec(*sh(p.shell,cmd),cwd=str(cwd),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True)
      async def rd(st,k):
       while line:=await st.readline():await emit(i,k,line.decode(errors="replace"))
      await asyncio.wait_for(asyncio.gather(rd(proc.stdout,"stdout"),rd(proc.stderr,"stderr"),proc.wait()),s.timeout)
      step_code=proc.returncode
     except asyncio.TimeoutError:
      if proc:
       kill_process_group(proc)
       await proc.wait()
      step_code=124;await emit(i,"stderr",f"[{s.name}] 超时\n")
     except Exception as e:
      step_code=1;await emit(i,"stderr",f"[{s.name}] {e}\n")
     step_failed=step_code!=0
     if step_failed:await emit(i,"system",f"[{s.name}] 失败 exit={step_code}\n")
     else:await emit(i,"system",f"[{s.name}] 完成\n")
    if step_failed:
     ok=False;code=step_code
     if not s.continue_on_error:break
   await emit(i,"system",f"\n部署{'成功' if ok else '失败'}\n")
   await finish(i,"success" if ok else "failed",code)
   finished=True
  except asyncio.CancelledError:
   if proc and proc.returncode is None:
    kill_process_group(proc)
    await proc.wait()
   if not finished:
    await finish(i,"failed",130)
    await emit(i,"stderr","部署任务被取消\n")
   raise
  except Exception as e:
   if not finished:
    await finish(i,"failed",1)
    await emit(i,"stderr",f"部署任务异常: {e}\n")

@app.post("/api/projects/{pid}/deploy")
async def deploy(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin","operator"))):
 p=d.get(Project,pid)
 if not p or not p.enabled:raise HTTPException(404,"项目不存在或已禁用")
 if locks[pid].locked():raise HTTPException(409,"该项目正在部署")
 j=Deployment(project_id=pid,user_id=u.id);d.add(j);d.commit();d.refresh(j);asyncio.create_task(run(j.id));return {"id":j.id,"status":"pending"}
@app.get("/api/deployments")
def deployments(project_id:int|None=None,status:str|None=None,page:int=1,page_size:int=20,d:Session=Depends(dbdep),u=Depends(user)):
 page=max(1,page);page_size=max(1,min(page_size,100))
 q=d.query(Deployment,Project.name,User.username).outerjoin(Project,Project.id==Deployment.project_id).outerjoin(User,User.id==Deployment.user_id)
 if project_id is not None:q=q.filter(Deployment.project_id==project_id)
 if status is not None:
  if status not in ("pending","running","success","failed"):raise HTTPException(400,"状态无效")
  q=q.filter(Deployment.status==status)
 total=q.count()
 rows=q.order_by(Deployment.id.desc()).offset((page-1)*page_size).limit(page_size).all()
 return {"total":total,"page":page,"page_size":page_size,"items":[{"id":j.id,"project_id":j.project_id,"project_name":project_name or f"项目 #{j.project_id}","user_id":j.user_id,"username":username or "-","status":j.status,"exit_code":j.exit_code,"created_at":j.created_at,"started_at":j.started_at,"finished_at":j.finished_at} for j,project_name,username in rows]}

@app.get("/api/deployments/{did}")
def deployment(did:int,d:Session=Depends(dbdep),u=Depends(user)):
 row=d.query(Deployment,Project.name,User.username).outerjoin(Project,Project.id==Deployment.project_id).outerjoin(User,User.id==Deployment.user_id).filter(Deployment.id==did).first()
 if not row:raise HTTPException(404,"部署不存在")
 j,project_name,username=row
 return {"id":j.id,"project_id":j.project_id,"project_name":project_name or f"项目 #{j.project_id}","user_id":j.user_id,"username":username or "-","status":j.status,"exit_code":j.exit_code,"created_at":j.created_at,"started_at":j.started_at,"finished_at":j.finished_at}
@app.get("/api/deployments/{did}/logs")
def logs(did:int,d:Session=Depends(dbdep),u=Depends(user)):return [{"id":x.id,"stream":x.stream,"message":x.message} for x in d.query(Log).filter_by(deployment_id=did).order_by(Log.id)]
@app.get("/api/projects/{pid}/yaml")
def yaml_export(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin","operator","viewer"))):
 p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 return yaml.safe_dump({"name":p.name,"branch":p.branch,"shell":p.shell,"steps":[{"name":s.name,"type":s.step_type,"cwd":s.cwd,"command":s.command,"enabled":s.enabled,"timeout":s.timeout,"continue_on_error":s.continue_on_error} for s in p.steps]},allow_unicode=True,sort_keys=False)
@app.websocket("/ws/deployments/{did}")
async def ws(w:WebSocket,did:int):
 if not w.scope.get("session",{}).get("user_id"):
  await w.close(code=1008);return
 await w.accept();q=asyncio.Queue();queues[did].add(q)
 try:
  d=SessionLocal();j=d.get(Deployment,did);rows=d.query(Log).filter_by(deployment_id=did).order_by(Log.id).all();d.close()
  if not j:
   await w.close(code=1008);return
  await w.send_json({"type":"connected","deployment_id":did,"status":j.status,"exit_code":j.exit_code})
  await w.send_json({"type":"snapshot","logs":[{"id":x.id,"stream":x.stream,"message":x.message} for x in rows]})
  while True:
   try:await w.send_json(await asyncio.wait_for(q.get(),10))
   except asyncio.TimeoutError:await w.send_json({"type":"ping"})
 except WebSocketDisconnect:pass
 finally:queues[did].discard(q)


@app.get("/{path:path}")
def frontend(path:str):
 target=STATIC_DIR/path
 if target.is_file(): return FileResponse(target)
 html=target/"index.html"
 if html.is_file(): return FileResponse(html)
 index=STATIC_DIR/"index.html"
 if index.is_file(): return FileResponse(index)
 raise HTTPException(404,"前端文件不存在")
