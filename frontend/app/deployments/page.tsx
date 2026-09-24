"use client";

import {useEffect,useState} from "react";
import {useSearchParams} from "next/navigation";

const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
const WS=process.env.NEXT_PUBLIC_WS_URL||"ws://localhost:8000";

export default function Page(){
 const params=useSearchParams(); const id=params.get("id"); const[logs,setLogs]=useState(""); const[status,setStatus]=useState("");
 useEffect(()=>{if(!id)return;let socket:WebSocket|undefined;let cancelled=false;
 fetch(API+"/api/deployments/"+id+"/logs",{credentials:"include"}).then(r=>r.json()).then(data=>setLogs(data.map((item:any)=>item.message).join("")));
 fetch(API+"/api/deployments/"+id,{credentials:"include"}).then(r=>r.json()).then(data=>setStatus(data.status));
 socket=new WebSocket(WS+"/ws/deployments/"+id);socket.onmessage=e=>{const data=JSON.parse(e.data);if(data.type==="snapshot")setLogs(data.logs.map((item:any)=>item.message).join(""));if(data.type==="log")setLogs(v=>v+data.message)};
 return()=>{cancelled=true;socket?.close()};
 },[id]);
 if(!id)return <main className="wrap">缺少部署 ID</main>;
 return <main className="wrap"><h1>部署 #{id} {status}</h1><pre>{logs}</pre><a href="/">← 返回</a></main>;
}
