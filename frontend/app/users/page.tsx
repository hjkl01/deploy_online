"use client";

import{useEffect,useState}from"react";
const API=process.env.NEXT_PUBLIC_API_URL||"";
const empty={username:"",password:"",role:"viewer"};

export default function Users(){
 const[users,setUsers]=useState<any[]>([]),[form,setForm]=useState<any>(null);
 const load=()=>fetch(API+"/api/users",{credentials:"include"}).then(async r=>{if(r.status===403){alert("没有权限");return []}return r.json()}).then(setUsers);
 useEffect(()=>{load()},[]);
 const save=async()=>{const edit=form.id!=null;const r=await fetch(API+(edit?"/api/users/"+form.id:"/api/users"),{method:edit?"PUT":"POST",headers:{"Content-Type":"application/json"},credentials:"include",body:JSON.stringify(form)});if(!r.ok){alert((await r.json()).detail||"保存失败");return}setForm(null);load()};
 const remove=async(id:number)=>{if(!confirm("确定删除这个用户吗？"))return;const r=await fetch(API+"/api/users/"+id,{method:"DELETE",credentials:"include"});if(!r.ok)alert((await r.json()).detail||"删除失败");else load()};
 return <main className="wrap"><div className="topbar"><h1>用户管理</h1><div><button onClick={()=>setForm({...empty})}>+ 添加用户</button> <a href="/projects">项目</a> <a href="/">首页</a></div></div>
 {form&&<div className="card"><h2>{form.id?"编辑用户":"添加用户"}</h2><label>用户名</label><input value={form.username} onChange={e=>setForm({...form,username:e.target.value})}/><label>{form.id?"新密码（留空不修改）":"密码"}</label><input type="password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/><label>角色</label><select value={form.role} onChange={e=>setForm({...form,role:e.target.value})}><option value="admin">管理员</option><option value="operator">操作员</option><option value="viewer">查看者</option></select><div className="actions"><button onClick={save}>保存</button><button className="secondary" onClick={()=>setForm(null)}>取消</button></div></div>}
 {users.map(u=><div className="card" key={u.id}><div className="row"><div><strong>{u.username}</strong><span>　{u.role==="admin"?"管理员":u.role==="operator"?"操作员":"查看者"}</span></div><div><button onClick={()=>setForm({...u,password:""})}>编辑</button> <button className="danger" onClick={()=>remove(u.id)}>删除</button></div></div></div>)}
 </main>
}