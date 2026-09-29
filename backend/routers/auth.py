import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from dependencies import dbdep, user
from models import User
from runtime import login_attempts
from schemas import Login
from security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(x: Login, request: Request, d: Session = Depends(dbdep)):
    key = f"{request.client.host if request.client else '-'}:{x.username}"
    now_ts = time.time()
    login_attempts[key] = [t for t in login_attempts[key] if now_ts - t < 60]
    if len(login_attempts[key]) >= 5:
        raise HTTPException(429, "登录失败次数过多，请 1 分钟后再试")

    u = d.query(User).filter_by(username=x.username).first()
    if not u or not verify_password(x.password, u.password_hash):
        login_attempts[key].append(now_ts)
        raise HTTPException(401, "用户名或密码错误")

    login_attempts.pop(key, None)
    request.session["user_id"] = u.id
    return {"id": u.id, "username": u.username, "role": u.role}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(u=Depends(user)):
    return {"id": u.id, "username": u.username, "role": u.role}
