"use client";

import {useEffect,useRef,useState} from "react";

const API=process.env.NEXT_PUBLIC_API_URL||"";
const WS=process.env.NEXT_PUBLIC_WS_URL||"";

function time(v:string|null){return v?new Date(v).toLocaleString():"-"}
function statusName(v:string){return v==="success"?"成功":v==="failed"?"失败":v==="running"?"运行中":v==="pending"?"等待中":v}
function duration(x:any){
 if(!x.started_at)return "-";
 const end=x.finished_at?new Date(x.finished_at).getTime():Date.now();
 const sec=Math.max(0,Math.floor((end-new Date(x.started_at).getTime())/1000));
 return sec<60?`${sec} 秒`:`${Math.floor(sec/60)} 分 ${sec%60} 秒`;
}

export default function Page(){
 const[id,setId]=useState<string|null>(null);
 useEffect(()=>{setId(new URLSearchParams(window.location.search).get("id"))},[]);
 return id?<Detail id={id}/>:<History/>;
}

function History(){
 const[rows,setRows]=useState<any[]>([]),[projects,setProjects]=useState<any[]>([]),[loading,setLoading]=useState(true);
 const[projectId,setProjectId]=useState(""),[filterStatus,setFilterStatus]=useState(""),[page,setPage]=useState(1),[total,setTotal]=useState(0);
 const pageSize=20;
 const load=()=>{
  setLoading(true);
  const q=new URLSearchParams({page:String(page),page_size:String(pageSize)});
  if(projectId)q.set("project_id",projectId);if(filterStatus)q.set("status",filterStatus);
  fetch(API+"/api/deployments?"+q.toString(),{credentials:"include"}).then(async r=>{if(r.status===401){window.location.href="/";return}if(r.ok){const x=await r.json();setRows(x.items);setTotal(x.total)}}).finally(()=>setLoading(false));
 };
 useEffect(()=>{fetch(API+"/api/projects",{credentials:"include"}).then(r=>r.ok?r.json():[]).then(setProjects)},[]);
 useEffect(()=>{load()},[page,projectId,filterStatus]);
 return <main className="wrap"><div className="topbar"><h1>部署记录</h1><div><a href="/">首页</a><a href="/projects">项目管理</a></div></div>
  <div className="card filters"><select value={projectId} onChange={e=>{setProjectId(e.target.value);setPage(1)}}><option value="">全部项目</option>{projects.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select><select value={filterStatus} onChange={e=>{setFilterStatus(e.target.value);setPage(1)}}><option value="">全部状态</option><option value="pending">等待中</option><option value="running">运行中</option><option value="success">成功</option><option value="failed">失败</option></select></div>
  {loading&&<div className="card">加载中...</div>}
  {!loading&&rows.length===0&&<div className="card">暂无符合条件的部署记录。</div>}
  {rows.map(x=><div className="card" key={x.id}><div className="row"><div><h2>{x.project_name} <span className={"status "+x.status}>{statusName(x.status)}</span></h2><p>部署 #{x.id} · 操作人：{x.username}</p><p>开始：{time(x.started_at||x.created_at)} · 结束：{time(x.finished_at)} · 耗时：{duration(x)}</p>{x.exit_code!==null&&<p>退出码：{x.exit_code}</p>}</div><div><a className="button-link" href={"/deployments?id="+x.id}>查看日志</a></div></div></div>)}
  <div className="pagination"><button disabled={page<=1} onClick={()=>setPage(page-1)}>上一页</button><span>第 {page} 页，共 {Math.max(1,Math.ceil(total/pageSize))} 页（{total} 条）</span><button disabled={page>=Math.ceil(total/pageSize)} onClick={()=>setPage(page+1)}>下一页</button></div>
 </main>
}

function Detail({id}:{id:string}){
 const[logs,setLogs]=useState(""),[status,setStatus]=useState(""),[info,setInfo]=useState<any>(null);
 const statusRef=useRef("");
 const logIdsRef=useRef<Set<number>>(new Set());
 useEffect(()=>{fetch(API+"/api/deployments/"+id,{credentials:"include"}).then(async r=>{if(r.status===401){window.location.href="/";return}if(r.ok)setInfo(await r.json())})},[id]);
 useEffect(()=>{let socket:WebSocket|undefined;let timer:ReturnType<typeof setTimeout>|undefined;let closed=false;
  logIdsRef.current.clear();
  const wsBase=WS||((window.location.protocol==="https:"?"wss://":"ws://")+window.location.host);
  const connect=()=>{if(closed)return;socket=new WebSocket(wsBase+"/ws/deployments/"+id);
   socket.onmessage=e=>{const data=JSON.parse(e.data);
    if(data.type==="connected"){statusRef.current=data.status;setStatus(data.status);if(data.status==="success"||data.status==="failed"){socket?.close();return}}
    if(data.type==="snapshot"){const ids=new Set<number>();const text=data.logs.map((item:any)=>{ids.add(item.id);return item.message}).join("");logIdsRef.current=ids;setLogs(text)}
    if(data.type==="log"){if(data.id!=null&&logIdsRef.current.has(data.id))return;if(data.id!=null)logIdsRef.current.add(data.id);setLogs(v=>v+data.message)}
    if(data.type==="status"){statusRef.current=data.status;setStatus(data.status);setInfo((v:any)=>v?{...v,status:data.status,exit_code:data.exit_code}:v);if(data.status==="success"||data.status==="failed")socket?.close()}
   };
   socket.onclose=()=>{if(!closed&&statusRef.current!=="success"&&statusRef.current!=="failed")timer=setTimeout(connect,1500)};
  };
  connect();
  return()=>{closed=true;if(timer)clearTimeout(timer);socket?.close()};
 },[id]);
 return <main className="wrap"><div className="topbar"><div><h1>部署 #{id} <span className={"status "+status}>{statusName(status)}</span></h1>{info&&<p>项目 {info.project_name||("#"+info.project_id)} · 操作人：{info.username} · 开始：{time(info.started_at||info.created_at)} · 结束：{time(info.finished_at)} · 耗时：{duration(info)}{info.exit_code!==null&&info.exit_code!==undefined?" · 退出码："+info.exit_code:""}</p>}</div><div><a href="/deployments">部署记录</a><a href="/">首页</a></div></div><pre>{logs}</pre></main>;
}