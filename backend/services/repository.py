from sqlalchemy.orm import Session

from models import Deployment, DeploymentStep, Env, Log, Project, Step, User


def list_users(d: Session):
    return d.query(User).order_by(User.id).all()


def get_user(d: Session, user_id: int):
    return d.get(User, user_id)


def username_exists(d: Session, username: str, exclude_id: int | None = None):
    q = d.query(User).filter(User.username == username)
    if exclude_id is not None:
        q = q.filter(User.id != exclude_id)
    return q.first() is not None


def admin_count(d: Session):
    return d.query(User).filter_by(role="admin").count()


def get_project(d: Session, project_id: int):
    return d.get(Project, project_id)


def project_has_deployments(d: Session, project_id: int):
    return d.query(Deployment.id).filter_by(project_id=project_id).first() is not None


def replace_project_children(d: Session, project: Project, steps_data, env_data):
    existing_secret = {
        e.key: e.value
        for e in d.query(Env).filter_by(project_id=project.id, is_secret=True).all()
    }
    d.query(Step).filter_by(project_id=project.id).delete(synchronize_session=False)
    d.query(Env).filter_by(project_id=project.id).delete(synchronize_session=False)
    for position, data in enumerate(steps_data):
        d.add(Step(project_id=project.id, position=position, **data))
    for data in env_data:
        d.add(Env(project_id=project.id, **data))
    return existing_secret


def list_deployment_steps(d: Session, deployment_id: int):
    return d.query(DeploymentStep).filter_by(deployment_id=deployment_id).order_by(DeploymentStep.position).all()


def get_deployment(d: Session, deployment_id: int):
    return d.get(Deployment, deployment_id)


def get_deployment_with_names(d: Session, deployment_id: int):
    return (
        d.query(Deployment, Project.name, User.username)
        .outerjoin(Project, Project.id == Deployment.project_id)
        .outerjoin(User, User.id == Deployment.user_id)
        .filter(Deployment.id == deployment_id)
        .first()
    )


def list_deployment_logs(d: Session, deployment_id: int):
    return d.query(Log).filter_by(deployment_id=deployment_id).order_by(Log.id).all()
