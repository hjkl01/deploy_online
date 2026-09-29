from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from dependencies import dbdep, role
from models import User
from schemas import UserIn
from security import hash_password
from services.repository import admin_count, get_user, list_users, username_exists

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def users(d: Session = Depends(dbdep), u=Depends(role("admin"))):
    return [{"id": x.id, "username": x.username, "role": x.role} for x in list_users(d)]


@router.post("")
def create_user(x: UserIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    username = x.username.strip()
    if not username or not x.password:
        raise HTTPException(400, "用户名和密码不能为空")
    if x.role not in ("admin", "operator", "viewer"):
        raise HTTPException(400, "角色无效")
    if len(x.password.encode()) > 72:
        raise HTTPException(400, "密码不能超过 72 字节")
    if username_exists(d, username):
        raise HTTPException(409, "用户名已存在")
    v = User(username=username, password_hash=hash_password(x.password), role=x.role)
    d.add(v)
    d.commit()
    d.refresh(v)
    return {"id": v.id, "username": v.username, "role": v.role}


@router.put("/{uid}")
def update_user(uid: int, x: UserIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    username = x.username.strip()
    v = get_user(d, uid)
    if not v:
        raise HTTPException(404, "用户不存在")
    if not username or x.role not in ("admin", "operator", "viewer"):
        raise HTTPException(400, "用户信息无效")
    if username_exists(d, username, uid):
        raise HTTPException(409, "用户名已存在")
    v.username = username
    v.role = x.role
    if x.password:
        if len(x.password.encode()) > 72:
            raise HTTPException(400, "密码不能超过 72 字节")
        v.password_hash = hash_password(x.password)
    d.commit()
    return {"id": v.id, "username": v.username, "role": v.role}


@router.delete("/{uid}")
def delete_user(uid: int, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    if uid == u.id:
        raise HTTPException(400, "不能删除当前登录用户")
    v = d.get(User, uid)
    if not v:
        raise HTTPException(404, "用户不存在")
    if v.role == "admin" and admin_count(d) <= 1:
        raise HTTPException(400, "至少保留一个管理员")
    d.delete(v)
    d.commit()
    return {"ok": True}
