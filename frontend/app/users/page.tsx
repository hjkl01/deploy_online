"use client";

import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "";
const EMPTY = { username: "", password: "", role: "viewer" };

const ROLE_META: Record<string, { label: string; tone: string; description: string; permissions: string[] }> = {
  admin: {
    label: "管理员",
    tone: "admin",
    description: "负责平台账号、项目配置与部署操作。",
    permissions: ["用户管理", "项目配置", "执行部署"],
  },
  operator: {
    label: "操作员",
    tone: "operator",
    description: "负责执行部署并查看部署记录。",
    permissions: ["执行部署", "查看项目", "查看记录"],
  },
  viewer: {
    label: "查看者",
    tone: "viewer",
    description: "只查看项目与部署状态，不执行变更。",
    permissions: ["查看项目", "查看记录"],
  },
};

type User = { id: number; username: string; role: string };

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState<any>(null);
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch(API + "/api/users", { credentials: "include" });
      if (r.status === 403) {
        setAllowed(false);
        return;
      }
      if (r.status === 401) {
        window.location.href = "/";
        return;
      }
      if (!r.ok) throw new Error("加载用户失败");
      setAllowed(true);
      setUsers(await r.json());
    } catch (e: any) {
      setError(e.message || "加载用户失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const counts = useMemo(() => ({
    total: users.length,
    admin: users.filter((u) => u.role === "admin").length,
    operator: users.filter((u) => u.role === "operator").length,
    viewer: users.filter((u) => u.role === "viewer").length,
  }), [users]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return users.filter((u) => {
      const matchesQuery = !q || u.username.toLowerCase().includes(q);
      const matchesRole = roleFilter === "all" || u.role === roleFilter;
      return matchesQuery && matchesRole;
    });
  }, [users, query, roleFilter]);

  if (allowed === false) {
    return (
      <main className="wrap">
        <div className="card permission-empty">
          <div className="permission-icon">!</div>
          <h1>暂无访问权限</h1>
          <p>用户管理仅对管理员开放。</p>
          <a className="button-link" href="/">返回首页</a>
        </div>
      </main>
    );
  }

  const save = async () => {
    setError("");
    if (!form.username.trim()) {
      setError("用户名不能为空");
      return;
    }
    if (!form.id && !form.password) {
      setError("新用户必须设置密码");
      return;
    }
    if (form.password && new TextEncoder().encode(form.password).length > 72) {
      setError("密码不能超过 72 字节");
      return;
    }

    setSaving(true);
    try {
      const edit = form.id != null;
      const r = await fetch(API + (edit ? "/api/users/" + form.id : "/api/users"), {
        method: edit ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(form),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setError(body.detail || "保存失败");
        return;
      }
      setForm(null);
      await load();
    } finally {
      setSaving(false);
    }
  };

  const remove = async (user: User) => {
    if (!confirm(`确定删除用户“${user.username}”吗？此操作不可撤销。`)) return;
    const r = await fetch(API + "/api/users/" + user.id, {
      method: "DELETE",
      credentials: "include",
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      setError(body.detail || "删除失败");
      return;
    }
    load();
  };

  return (
    <main className="wrap">
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div>
            <div className="brand-title">用户与权限</div>
            <p>管理平台访问账号与角色</p>
          </div>
        </div>
        <div>
          <a href="/">首页</a>
          <a href="/projects">项目</a>
          <a href="/deployments">部署记录</a>
          <button onClick={() => { setError(""); setForm({ ...EMPTY }); }}>+ 添加用户</button>
        </div>
      </div>

      <section className="users-hero">
        <div>
          <div className="hero-kicker">ACCESS CONTROL</div>
          <h1>账号与权限</h1>
          <p>集中管理平台成员，并通过角色控制可执行的操作范围。</p>
        </div>
        <div className="user-summary">
          <div><strong>{counts.total}</strong><span>全部用户</span></div>
          <div><strong>{counts.admin}</strong><span>管理员</span></div>
          <div><strong>{counts.operator}</strong><span>操作员</span></div>
          <div><strong>{counts.viewer}</strong><span>查看者</span></div>
        </div>
      </section>

      <section className="role-grid">
        {Object.entries(ROLE_META).map(([key, role]) => (
          <button
            key={key}
            className={`role-card ${role.tone} ${roleFilter === key ? "selected" : ""}`}
            onClick={() => setRoleFilter(roleFilter === key ? "all" : key)}
          >
            <div className="role-card-head">
              <span className="role-symbol">{key === "admin" ? "A" : key === "operator" ? "O" : "V"}</span>
              <span className={`role-badge ${role.tone}`}>{role.label}</span>
              <strong>{counts[key as "admin" | "operator" | "viewer"]}</strong>
            </div>
            <p>{role.description}</p>
            <div className="permission-tags">
              {role.permissions.map((item) => <span key={item}>{item}</span>)}
            </div>
          </button>
        ))}
      </section>

      <section className="section-title users-section-title">
        <div>
          <h2>成员列表 <span className="badge">{filtered.length} 个</span></h2>
          <p>点击角色卡片可以快速筛选成员。</p>
        </div>
      </section>

      <div className="users-toolbar">
        <div className="search-box">
          <span>⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索用户名..." />
        </div>
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="all">全部角色</option>
          <option value="admin">管理员</option>
          <option value="operator">操作员</option>
          <option value="viewer">查看者</option>
        </select>
      </div>

      {error && <div className="editor-error">{error}</div>}

      {form && (
        <div className="user-form-card card">
          <div className="section-heading">
            <div>
              <span className="section-index">{form.id ? "✎" : "+"}</span>
              <div>
                <h2>{form.id ? "编辑用户" : "添加用户"}</h2>
                <p>{form.id ? "修改账号角色或重置密码。" : "创建一个新的平台访问账号。"}</p>
              </div>
            </div>
            <button className="secondary" onClick={() => setForm(null)}>取消</button>
          </div>
          <div className="form-grid">
            <div>
              <label>用户名</label>
              <input autoFocus value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="例如 deployer" />
            </div>
            <div>
              <label>{form.id ? "新密码" : "密码"}</label>
              <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder={form.id ? "留空则保持原密码" : "设置登录密码"} />
            </div>
            <div>
              <label>角色</label>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="admin">管理员</option>
                <option value="operator">操作员</option>
                <option value="viewer">查看者</option>
              </select>
            </div>
          </div>
          <div className="form-role-hint">
            <span className={`role-symbol small ${ROLE_META[form.role].tone}`}>{form.role === "admin" ? "A" : form.role === "operator" ? "O" : "V"}</span>
            <div><strong>{ROLE_META[form.role].label}</strong><span>{ROLE_META[form.role].description}</span></div>
          </div>
          <div className="actions">
            <button onClick={save} disabled={saving}>{saving ? "保存中..." : "保存用户"}</button>
            <button className="secondary" onClick={() => setForm(null)}>取消</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="card empty">正在加载用户...</div>
      ) : filtered.length === 0 ? (
        <div className="card empty">{users.length ? "没有匹配的用户" : "还没有用户"}</div>
      ) : (
        <div className="users-list">
          {filtered.map((u) => {
            const role = ROLE_META[u.role] || ROLE_META.viewer;
            return (
              <div className="user-row card" key={u.id}>
                <div className={`user-avatar ${role.tone}`}>{u.username.slice(0, 1).toUpperCase()}</div>
                <div className="user-main">
                  <strong>{u.username}</strong>
                  <span>ID #{u.id}</span>
                </div>
                <div className="user-role-cell">
                  <span className={`role-badge ${role.tone}`}>{role.label}</span>
                  <small>{role.description}</small>
                </div>
                <div className="user-actions">
                  <button className="secondary" onClick={() => { setError(""); setForm({ ...u, password: "" }); }}>编辑</button>
                  <button className="danger" onClick={() => remove(u)}>删除</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
