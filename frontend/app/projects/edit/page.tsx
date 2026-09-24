"use client";

import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";

const API=process.env.NEXT_PUBLIC_API_URL||"";
const emptyStep={name:"",step_type:"command",cwd:"~/",command:"",enabled:true,timeout:3600,continue_on_error:false};

export default function Edit(){
 const r=useRouter(); const[id,setId]=useState<string|null>(null); const[p,setP]=useState<any>(null);
 useEffect(()=>{setId(new URLSearchParams(window.location.search).get("id"))},[]);
 useEffect(()=>{if(!id)return;fetch(API+"/api/projects/"+id,{credentials:"include"}).then(x=>x.json()).then(setP)},[id]);
 if(!id)return <main className="wrap">缺少项目 ID</main>;
 if(!p)return <main className="wrap">加载中...</main>;
 const save=async()=>{const x=await fetch(API+"/api/projects/"+id,{method:"PUT",headers:{"Content-Type":"application/json"},credentials:"include",body:JSON.stringify({...p,steps:p.steps.map((s:any)=>{const{position,id,...v}=s;return v}),environment:p.environment.map((e:any)=>{const{id,...v}=e;return v})})});if(!x.ok){alert((await x.json()).detail||"保存失败");return}r.push("/")};
 return <main className="wrap"><h1>编辑项目：{p.name}</h1>
 <div className="card"><label>项目名称</label><input value={p.name} onChange={e=>setP({...p,name:e.target.value})}/><label>说明</label><input value={p.description} onChange={e=>setP({...p,description:e.target.value})}/><label>Git 分支</label><input value={p.branch} onChange={e=>setP({...p,branch:e.target.value})}/><label>Shell</label><select value={p.shell} onChange={e=>setP({...p,shell:e.target.value})}><option value="bash">bash</option><option value="zsh">zsh</option></select></div>
 <h2>部署步骤</h2>{p.steps.map((s:any,i:number)=><div className="card" key={i}><div className="row"><h3>Step {i+1}</h3><button className="danger" onClick={()=>setP({...p,steps:p.steps.filter((_:any,j:number)=>j!==i)})}>删除</button></div><label>名称</label><input value={s.name} onChange={e=>{s.name=e.target.value;setP({...p})}}/><label>类型</label><select value={s.step_type} onChange={e=>{s.step_type=e.target.value;setP({...p})}}><option value="command">command</option><option value="git_pull">git pull</option></select><label>cwd（必须从 ~/ 开始）</label><input value={s.cwd} onChange={e=>{s.cwd=e.target.value;setP({...p})}}/><label>命令</label><textarea value={s.command} disabled={s.step_type==="git_pull"} onChange={e=>{s.command=e.target.value;setP({...p})}}/><label>超时秒数</label><input type="number" value={s.timeout} onChange={e=>{s.timeout=Number(e.target.value);setP({...p})}}/></div>)}
 <button onClick={()=>setP({...p,steps:[...p.steps,{...emptyStep}]})}>+ 添加 Step</button><h2>环境变量</h2>{p.environment.map((e:any,i:number)=><div className="card" key={"env"+i}><div className="row"><input placeholder="KEY" value={e.key} onChange={x=>{e.key=x.target.value;setP({...p})}}/><input placeholder="VALUE" type={e.is_secret?"password":"text"} value={e.value} onChange={x=>{e.value=x.target.value;setP({...p})}}/><button className="danger" onClick={()=>setP({...p,environment:p.environment.filter((_:any,j:number)=>j!==i)})}>删除</button></div></div>)}<button onClick={()=>setP({...p,environment:[...p.environment,{key:"",value:"",is_secret:false}]})}>+ 添加环境变量</button><button className="secondary" onClick={save} style={{marginLeft:10}}>保存</button></main>;
}
