"use client";

import{useEffect,useState}from"react";
import{useRouter}from"next/navigation";

const API=process.env.NEXT_PUBLIC_API_URL||"";

export default function Home(){
 const[p,setP]=useState<any[]>([]),[me,setMe]=useState<any>(null),[login,setLogin]=useState(false);
 const r=useRouter();
 const load=()=>Promise.all([fetch(API+"/api/projects",{credentials:"include"}),fetch(API+"/api/auth/me",{credentials:"include"})]).then(async([a,b])=>{
   if(a.status===401){setLogin(true);return}
   setP(await a.json());if(b.ok)setMe(await b.json())
 }).catch(()=>setLogin(true));
 useEffect(()=>{load()},[]);
 if(login)return <Login onLogin={()=>{setLogin(false);load()}}/>;
 return <main className="wrap">
   <div className="topbar">
    <div className="brand"><div className="brand-mark">D</div><div><div className="brand-title">Deploy Online</div><p>{me?"你好，"+me.username+" · "+roleName(me.role):"部署管理平台"}</p></div></div>
    <div><a href="/projects">项目</a><a href="/deployments">部署记录</a>{me?.role==="admin"&&<a href="/users">用户</a>}<button className="secondary" onClick={async()=>{await fetch(API+"/api/auth/logout",{method:"POST",credentials:"include"});setLogin(true)}}>退出</button></div>
   </div>
   <div className="section-title"><div><h2>项目概览</h2><span className="badge">{p.length} 个项目</span></div>{me?.role==="admin"&&<button onClick={()=>r.push("/projects/edit")}>+ 添加项目</button>}</div>
   <div className="grid">{p.map(x=><Project key={x.id} p={x} router={r} canDeploy={me?.role==="admin"||me?.role==="operator"}/>)}</div>
   {p.length===0&&<div className="card empty"><h3>还没有项目</h3><p>创建第一个项目配置，就可以开始一键部署。</p>{me?.role==="admin"&&<button onClick={()=>r.push("/projects/edit")}>创建项目</button>}</div>}
 </main>
}

function roleName(x:string){return x==="admin"?"管理员":x==="operator"?"操作员":"查看者"}

function Login({onLogin}:{onLogin:()=>void}){
 const[u,su]=useState("admin"),[pw,sp]=useState(""),[err,se]=useState("");
 return <main className="login-shell">
   <section className="login-visual"><div className="brand"><div className="brand-mark">D</div><div className="brand-title">Deploy Online</div></div><h1>让部署变得简单、清晰、可控。</h1><p>集中管理项目配置、执行部署流程，并实时查看部署日志。</p><div className="login-points"><div>✓ 多项目、多步骤部署</div><div>✓ 实时部署状态与日志</div><div>✓ 基于角色的访问控制</div></div></section>
   <section className="login-panel"><div className="login-card"><div className="brand"><div className="brand-mark">D</div><div className="brand-title">Deploy Online</div></div><h2 style={{marginTop:24}}>欢迎回来</h2><p className="muted">登录你的部署控制台</p><label>用户名</label><input placeholder="请输入用户名" value={u} onChange={e=>su(e.target.value)}/><label>密码</label><input placeholder="请输入密码" type="password" value={pw} onChange={e=>sp(e.target.value)} onKeyDown={e=>{if(e.key==="Enter")document.getElementById("login-btn")?.click()}}/><button id="login-btn" onClick={async()=>{const r=await fetch(API+"/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"include",body:JSON.stringify({username:u,password:pw})});if(r.ok)onLogin();else se("用户名或密码错误")}}>登录</button>{err&&<p className="error">{err}</p>}</div></section>
 </main>
}

function Project({p,router,canDeploy}:{p:any,router:any,canDeploy:boolean}){
 return <div className="card project-card"><div className="project-icon">{p.name?.slice(0,1).toUpperCase()||"P"}</div><h2>{p.name}</h2><p>{p.description||"暂无项目说明"}</p><div className="project-meta"><span className={p.enabled?"badge enabled":"badge disabled"}>{p.enabled?"已启用":"已禁用"}</span><span className="badge">{p.shell}</span><span className="badge">{p.branch}</span></div><div className="project-actions">{canDeploy&&<button disabled={!p.enabled} onClick={async()=>{const x=await fetch(API+"/api/projects/"+p.id+"/deploy",{method:"POST",credentials:"include"});if(!x.ok){alert((await x.json()).detail);return}const d=await x.json();router.push("/deployments?id="+d.id)}}>{p.enabled?"立即部署":"项目已禁用"}</button>}</div></div>
}
