from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import SessionLocal
from models import User


def dbdep():
    d = SessionLocal()
    try:
        yield d
    finally:
        d.close()


def user(request: Request, d: Session = Depends(dbdep)):
    user_id = request.session.get("user_id")
    u = d.get(User, user_id) if user_id else None
    if not u:
        raise HTTPException(401, "未登录")
    return u


def role(*roles):
    def dep(u=Depends(user)):
        if u.role not in roles:
            raise HTTPException(403, "没有权限")
        return u
    return dep
