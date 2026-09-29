from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import ProjectMember, User


def require_project_deploy_access(d: Session, project_id: int, u: User):
    if u.role == "admin":
        return
    allowed = d.query(ProjectMember.id).filter_by(project_id=project_id, user_id=u.id).first()
    if not allowed:
        raise HTTPException(403, "你没有该项目的部署权限")
