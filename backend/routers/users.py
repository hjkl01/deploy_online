from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from dependencies import dbdep, role
from models import Project, ProjectMember, User
from schemas import UserIn
from security import hash_password
from services.repository import admin_count, get_user, list_users, username_exists

router = APIRouter(prefix="/api/users", tags=["users"])


def _validate_project_ids(d: Session, x: UserIn):
    project_ids = set(x.project_ids)
    if len(project_ids) != len(x.project_ids):
        raise HTTPException(400, "项目不能重复")
    if x.role != "operator":
        if project_ids:
            raise HTTPException(400, "只有操作员可以配置项目部署权限")
        return []
    if not project_ids:
        return []
    projects = d.query(Project).filter(Project.id.in_(project_ids)).all()
    if len(projects) != len(project_ids):
        raise HTTPException(400, "存在无效项目")
    return list(project_ids)


def _sync_project_members(d: Session, user_id: int, project_ids: list[int]):
    d.query(ProjectMember).filter_by(user_id=user_id).delete(synchronize_session=False)
    for project_id in project_ids:
        d.add(ProjectMember(project_id=project_id, user_id=user_id))


def _user_out(d: Session, user: User):
    memberships = (
        d.query(ProjectMember, Project)
        .join(Project, Project.id == ProjectMember.project_id)
        .filter(ProjectMember.user_id == user.id)
        .order_by(Project.name.asc())
        .all()
    )
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "project_ids": [member.project_id for member, _ in memberships],
        "projects": [{"id": project.id, "name": project.name} for _, project in memberships],
    }


@router.get("")
def users(d: Session = Depends(dbdep), u=Depends(role("admin"))):
    return [_user_out(d, x) for x in list_users(d)]


@router.post("")
def create_user(x: UserIn, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    username = x.username.strip()
    if not username or not x.password:
        raise HTTPException(400, "用户名和密码不能为空")
    if x.role not in ("admin", "operator", "viewer"):
        raise HTTPException(400, "角色无效")
    if len(x.password.encode()) > 72:
        raise HTTPException(400, "密码不能超过 72 字节")
    project_ids = _validate_project_ids(d, x)
    if username_exists(d, username):
        raise HTTPException(409, "用户名已存在")
    v = User(username=username, password_hash=hash_password(x.password), role=x.role)
    d.add(v)
    d.flush()
    _sync_project_members(d, v.id, project_ids)
    d.commit()
    d.refresh(v)
    return _user_out(d, v)


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
    if x.password:
        if len(x.password.encode()) > 72:
            raise HTTPException(400, "密码不能超过 72 字节")
        v.password_hash = hash_password(x.password)

    project_ids = _validate_project_ids(d, x)
    v.username = username
    v.role = x.role
    _sync_project_members(d, v.id, project_ids)
    d.commit()
    return _user_out(d, v)


@router.delete("/{uid}")
def delete_user(uid: int, d: Session = Depends(dbdep), u=Depends(role("admin"))):
    if uid == u.id:
        raise HTTPException(400, "不能删除当前登录用户")
    v = d.get(User, uid)
    if not v:
        raise HTTPException(404, "用户不存在")
    if v.role == "admin" and admin_count(d) <= 1:
        raise HTTPException(400, "至少保留一个管理员")
    d.query(ProjectMember).filter_by(user_id=uid).delete(synchronize_session=False)
    d.delete(v)
    d.commit()
    return {"ok": True}
