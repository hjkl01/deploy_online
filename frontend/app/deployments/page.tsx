"use client";

import {useEffect,useState} from "react";


const API=process.env.NEXT_PUBLIC_API_URL||"";
const WS=process.env.NEXT_PUBLIC_WS_URL||"";

export default function Page(){
 const[id,setId]=useState<string|null>(null); const[logs,setLogs]=useState(""); const[status,setStatus]=useState("");
 useEffect(()=>{setId(new URLSearchParams(window.location.search).get("id"))},[]);
 useEffect(()=>{if(!id)return;let socket:WebSocket|undefined;let timer:ReturnType<typeof setTimeout>|undefined;let closed=false;
 const wsBase=WS||((window.location.protocol==="https:"?"wss://":"ws://")+window.location.host);
 const connect=()=>{if(closed)return;socket=new WebSocket(wsBase+"/ws/deployments/"+id);
  socket.onmessage=e=>{const data=JSON.parse(e.data);if(data.type==="connected")setStatus(data.status);if(data.type==="snapshot")setLogs(data.logs.map((item:any)=>item.message).join(""));if(data.type==="log")setLogs(v=>v+data.message);if(data.type==="status"){setStatus(data.status);if(data.status==="success"||data.status==="failed")socket?.close()}};
  socket.onclose=()=>{if(!closed)timer=setTimeout(connect,1500)};
 };
 connect();
 return()=>{closed=true;if(timer)clearTimeout(timer);socket?.close()};
 },[id]);
 if(!id)return <main className="wrap">缺少部署 ID</main>;
 return <main className="wrap"><h1>部署 #{id} {status}</h1><pre>{logs}</pre><a href="/">← 返回</a></main>;
}
