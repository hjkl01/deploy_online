import asyncio,os,shlex
from datetime import datetime,timezone
from pathlib import Path
from collections import defaultdict
import yaml
from fastapi import FastAPI,Depends,HTTPException,Request,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel,Field
from pydantic_settings import BaseSettings
from passlib.context import CryptContext
from sqlalchemy import create_engine,Column,Integer,String,Text,Boolean,ForeignKey,DateTime
from sqlalchemy.orm import declarative_base,sessionmaker,Session,relationship

class Settings(BaseSettings):
 database_url:str="sqlite:///./data/deploy_online.db";secret_key:str="change-me";admin_username:str="admin";admin_password:str="admin"
settings=Settings();Path("data").mkdir(exist_ok=True)
engine=create_engine(settings.database_url,connect_args={"check_same_thread":False});SessionLocal=sessionmaker(bind=engine,expire_on_commit=False);Base=declarative_base();now=lambda:datetime.now(timezone.utc)
class User(Base):
 __tablename__="users";id=Column(Integer,primary_key=True);username=Column(String(100),unique=True);password_hash=Column(String(255));role=Column(String(20),default="viewer")
class Project(Base):
 __tablename__="projects";id=Column(Integer,primary_key=True);name=Column(String(200));description=Column(Text,default="");root_path=Column(String(1000));branch=Column(String(255),default="main");shell=Column(String(20),default="bash");enabled=Column(Boolean,default=True)
 steps=relationship("Step",cascade="all,delete-orphan",order_by="Step.position");envs=relationship("Env",cascade="all,delete-orphan")
class Step(Base):
 __tablename__="steps";id=Column(Integer,primary_key=True);project_id=Column(ForeignKey("projects.id"));name=Column(String(200));step_type=Column(String(30),default="command");cwd=Column(String(1000),default="~");command=Column(Text,default="");enabled=Column(Boolean,default=True);timeout=Column(Integer,default=3600);continue_on_error=Column(Boolean,default=False);position=Column(Integer,default=0)
class Env(Base):
 __tablename__="envs";id=Column(Integer,primary_key=True);project_id=Column(ForeignKey("projects.id"));key=Column(String(255));value=Column(Text,default="");is_secret=Column(Boolean,default=False)
class Deployment(Base):
 __tablename__="deployments";id=Column(Integer,primary_key=True);project_id=Column(Integer);user_id=Column(Integer);status=Column(String(30),default="pending");exit_code=Column(Integer);created_at=Column(DateTime,default=now);started_at=Column(DateTime);finished_at=Column(DateTime)
class Log(Base):
 __tablename__="logs";id=Column(Integer,primary_key=True);deployment_id=Column(Integer,index=True);stream=Column(String(20));message=Column(Text);created_at=Column(DateTime,default=now)
Base.metadata.create_all(engine);pwd=CryptContext(schemes=["bcrypt"],deprecated="auto")
d=SessionLocal()
if not d.query(User).filter_by(username=settings.admin_username).first():d.add(User(username=settings.admin_username,password_hash=pwd.hash(settings.admin_password),role="admin"));d.commit()
d.close()
class Login(BaseModel):username:str;password:str
class StepIn(BaseModel):
 name:str;step_type:str="command";cwd:str="~";command:str="";enabled:bool=True;timeout:int=Field(3600,ge=1,le=86400);continue_on_error:bool=False
class EnvIn(BaseModel):key:str;value:str="";is_secret:bool=False
class ProjectIn(BaseModel):
 name:str;description:str="";root_path:str;branch:str="main";shell:str="bash";enabled:bool=True;steps:list[StepIn]=[];environment:list[EnvIn]=[]
app=FastAPI(title="deploy_online");app.add_middleware(SessionMiddleware,secret_key=settings.secret_key)
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
 if not(x.root_path.startswith("~") or x.root_path.startswith("/")):raise HTTPException(400,"root_path 必须从 ~ 或绝对路径开始")
 for s in x.steps:
  if not(s.cwd.startswith("~") or s.cwd.startswith("/")):raise HTTPException(400,"cwd 必须从 ~ 或绝对路径开始")
def po(p):return {"id":p.id,"name":p.name,"description":p.description,"root_path":p.root_path,"branch":p.branch,"shell":p.shell,"enabled":p.enabled}
@app.get("/health")
def health():return {"status":"ok"}
@app.post("/api/auth/login")
def login(x:Login,request:Request,d:Session=Depends(dbdep)):
 u=d.query(User).filter_by(username=x.username).first()
 if not u or not pwd.verify(x.password,u.password_hash):raise HTTPException(401,"用户名或密码错误")
 request.session["user_id"]=u.id;return {"id":u.id,"username":u.username,"role":u.role}
@app.post("/api/auth/logout")
def logout(request:Request):request.session.clear();return {"ok":True}
@app.get("/api/auth/me")
def me(u=Depends(user)):return {"id":u.id,"username":u.username,"role":u.role}
@app.get("/api/projects")
def projects(d:Session=Depends(dbdep),u=Depends(role("admin","operator","viewer"))):return [po(p) for p in d.query(Project).order_by(Project.id.desc())]
@app.get("/api/projects/{pid}")
def project(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin","operator","viewer"))):
 p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 x=po(p);x["steps"]=[{"id":s.id,"name":s.name,"step_type":s.step_type,"cwd":s.cwd,"command":s.command,"enabled":s.enabled,"timeout":s.timeout,"continue_on_error":s.continue_on_error,"position":s.position} for s in p.steps];x["environment"]=[{"id":e.id,"key":e.key,"value":"" if e.is_secret else e.value,"is_secret":e.is_secret} for e in p.envs];return x
@app.post("/api/projects")
def create(x:ProjectIn,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 check(x);p=Project(name=x.name,description=x.description,root_path=x.root_path,branch=x.branch,shell=x.shell,enabled=x.enabled);d.add(p);d.flush()
 for i,s in enumerate(x.steps):d.add(Step(project_id=p.id,position=i,**s.model_dump()))
 for e in x.environment:d.add(Env(project_id=p.id,**e.model_dump()))
 d.commit();d.refresh(p);return po(p)
@app.put("/api/projects/{pid}")
def update(pid:int,x:ProjectIn,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 check(x);p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 p.name=x.name;p.description=x.description;p.root_path=x.root_path;p.branch=x.branch;p.shell=x.shell;p.enabled=x.enabled;d.query(Step).filter_by(project_id=pid).delete();d.query(Env).filter_by(project_id=pid).delete()
 for i,s in enumerate(x.steps):d.add(Step(project_id=pid,position=i,**s.model_dump()))
 for e in x.environment:d.add(Env(project_id=pid,**e.model_dump()))
 d.commit();return po(p)
@app.delete("/api/projects/{pid}")
def delete(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin"))):
 p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 d.delete(p);d.commit();return {"ok":True}
async def emit(i,stream,msg):
 d=SessionLocal();d.add(Log(deployment_id=i,stream=stream,message=msg));d.commit();d.close()
 for q in list(queues[i]):await q.put({"type":"log","stream":stream,"message":msg})
def finish(i,status,code):
 d=SessionLocal();j=d.get(Deployment,i);j.status=status;j.exit_code=code;j.finished_at=now();d.commit();d.close()
def sh(shell,cmd):return ["/bin/bash","-lc",cmd] if shell=="bash" else ["/bin/zsh","-lc",cmd]
async def run(i):
 d=SessionLocal();j=d.get(Deployment,i);p=d.get(Project,j.project_id);steps=d.query(Step).filter_by(project_id=p.id).order_by(Step.position).all();envs=d.query(Env).filter_by(project_id=p.id).all();d.close()
 async with locks[p.id]:
  d=SessionLocal();j=d.get(Deployment,i);j.status="running";j.started_at=now();d.commit();d.close();env=os.environ.copy();env.update({e.key:e.value for e in envs});ok=True;code=0
  if not Path(p.root_path).expanduser().is_dir():await emit(i,"stderr","项目根目录不存在\n");finish(i,"failed",1);return
  await emit(i,"system",f"开始部署 {p.name}\nShell: {p.shell}\n")
  for s in steps:
   if not s.enabled:continue
   cwd=Path(s.cwd).expanduser().resolve();cmd=("git checkout "+shlex.quote(p.branch)+" && git pull --ff-only") if s.step_type=="git_pull" else s.command
   if not cwd.is_dir():await emit(i,"stderr",f"[{s.name}] cwd 不存在: {cwd}\n");ok=False;code=1
   elif cmd.strip():
    await emit(i,"system",f"\n>>> {s.name}\n$ {cmd}\n");proc=None
    try:
     proc=await asyncio.create_subprocess_exec(*sh(p.shell,cmd),cwd=str(cwd),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
     async def rd(st,k):
      while line:=await st.readline():await emit(i,k,line.decode(errors="replace"))
     await asyncio.wait_for(asyncio.gather(rd(proc.stdout,"stdout"),rd(proc.stderr,"stderr"),proc.wait()),s.timeout);code=proc.returncode
    except asyncio.TimeoutError:
     if proc:proc.kill();await proc.wait()
     code=124;await emit(i,"stderr",f"[{s.name}] 超时\n")
    except Exception as e:code=1;await emit(i,"stderr",f"[{s.name}] {e}\n")
    if code:ok=False;await emit(i,"system",f"[{s.name}] 失败 exit={code}\n")
    else:await emit(i,"system",f"[{s.name}] 完成\n")
   if not ok and not s.continue_on_error:break
  finish(i,"success" if ok else "failed",code);await emit(i,"system",f"\n部署{'成功' if ok else '失败'}\n")
@app.post("/api/projects/{pid}/deploy")
async def deploy(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin","operator"))):
 p=d.get(Project,pid)
 if not p or not p.enabled:raise HTTPException(404,"项目不存在或已禁用")
 if locks[pid].locked():raise HTTPException(409,"该项目正在部署")
 j=Deployment(project_id=pid,user_id=u.id);d.add(j);d.commit();d.refresh(j);asyncio.create_task(run(j.id));return {"id":j.id,"status":"pending"}
@app.get("/api/deployments/{did}")
def deployment(did:int,d:Session=Depends(dbdep),u=Depends(user)):
 j=d.get(Deployment,did)
 if not j:raise HTTPException(404,"部署不存在")
 return {"id":j.id,"project_id":j.project_id,"status":j.status,"exit_code":j.exit_code,"created_at":j.created_at,"started_at":j.started_at,"finished_at":j.finished_at}
@app.get("/api/deployments/{did}/logs")
def logs(did:int,d:Session=Depends(dbdep),u=Depends(user)):return [{"id":x.id,"stream":x.stream,"message":x.message} for x in d.query(Log).filter_by(deployment_id=did).order_by(Log.id)]
@app.get("/api/projects/{pid}/yaml")
def yaml_export(pid:int,d:Session=Depends(dbdep),u=Depends(role("admin","operator","viewer"))):
 p=d.get(Project,pid)
 if not p:raise HTTPException(404,"项目不存在")
 return yaml.safe_dump({"name":p.name,"root_path":p.root_path,"branch":p.branch,"shell":p.shell,"steps":[{"name":s.name,"type":s.step_type,"cwd":s.cwd,"command":s.command,"enabled":s.enabled,"timeout":s.timeout,"continue_on_error":s.continue_on_error} for s in p.steps]},allow_unicode=True,sort_keys=False)
@app.websocket("/ws/deployments/{did}")
async def ws(w:WebSocket,did:int):
 await w.accept();q=asyncio.Queue();queues[did].add(q)
 try:
  await w.send_json({"type":"connected","deployment_id":did})
  while True:
   try:await w.send_json(await asyncio.wait_for(q.get(),10))
   except asyncio.TimeoutError:await w.send_json({"type":"ping"})
 except WebSocketDisconnect:pass
 finally:queues[did].discard(q)
