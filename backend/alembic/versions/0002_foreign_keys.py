"""add referential integrity and cascade rules"""
from alembic import op
import sqlalchemy as sa

revision = "0002_foreign_keys"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _copy_table(old, new, columns):
    op.execute(f"INSERT INTO {new} ({', '.join(columns)}) SELECT {', '.join(columns)} FROM {old}")


def upgrade() -> None:
    # Recreate affected SQLite tables so existing data is preserved while
    # adding explicit ON DELETE behavior.
    op.create_table(
        "projects_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200)),
        sa.Column("description", sa.Text()),
        sa.Column("branch", sa.String(255)),
        sa.Column("shell", sa.String(20)),
        sa.Column("enabled", sa.Boolean()),
    )
    _copy_table("projects", "projects_new", ["id", "name", "description", "branch", "shell", "enabled"])
    op.drop_table("projects")
    op.rename_table("projects_new", "projects")

    op.create_table(
        "users_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("role", sa.String(20)),
        sa.UniqueConstraint("username"),
    )
    _copy_table("users", "users_new", ["id", "username", "password_hash", "role"])
    op.drop_table("users")
    op.rename_table("users_new", "users")

    op.create_table(
        "steps_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer()),
        sa.Column("name", sa.String(200)),
        sa.Column("step_type", sa.String(30)),
        sa.Column("cwd", sa.String(1000)),
        sa.Column("command", sa.Text()),
        sa.Column("enabled", sa.Boolean()),
        sa.Column("timeout", sa.Integer()),
        sa.Column("continue_on_error", sa.Boolean()),
        sa.Column("position", sa.Integer()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    _copy_table("steps", "steps_new", ["id", "project_id", "name", "step_type", "cwd", "command", "enabled", "timeout", "continue_on_error", "position"])
    op.drop_table("steps")
    op.rename_table("steps_new", "steps")

    op.create_table(
        "envs_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer()),
        sa.Column("key", sa.String(255)),
        sa.Column("value", sa.Text()),
        sa.Column("is_secret", sa.Boolean()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    _copy_table("envs", "envs_new", ["id", "project_id", "key", "value", "is_secret"])
    op.drop_table("envs")
    op.rename_table("envs_new", "envs")

    op.create_table(
        "deployments_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer()),
        sa.Column("user_id", sa.Integer()),
        sa.Column("status", sa.String(30)),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("config_snapshot", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("cancel_requested", sa.Boolean()),
        sa.Column("before_sha", sa.String(64)),
        sa.Column("after_sha", sa.String(64)),
        sa.Column("retry_of", sa.Integer()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["retry_of"], ["deployments_new.id"], ondelete="SET NULL"),
    )
    _copy_table("deployments", "deployments_new", ["id", "project_id", "user_id", "status", "exit_code", "created_at", "started_at", "finished_at", "config_snapshot", "note", "cancel_requested", "before_sha", "after_sha", "retry_of"])
    op.drop_table("deployments")
    op.rename_table("deployments_new", "deployments")
    for name, cols in [
        ("ix_deployments_project_id", ["project_id"]),
        ("ix_deployments_user_id", ["user_id"]),
        ("ix_deployments_status", ["status"]),
        ("ix_deployments_created_at", ["created_at"]),
        ("ix_deployments_cancel_requested", ["cancel_requested"]),
        ("ix_deployments_project_created", ["project_id", "created_at"]),
        ("ix_deployments_status_created", ["status", "created_at"]),
    ]:
        op.create_index(name, "deployments", cols)

    op.create_table(
        "deployment_steps_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deployment_id", sa.Integer()),
        sa.Column("source_step_id", sa.Integer()),
        sa.Column("position", sa.Integer()),
        sa.Column("name", sa.String(200)),
        sa.Column("status", sa.String(30)),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_step_id"], ["steps.id"], ondelete="SET NULL"),
    )
    _copy_table("deployment_steps", "deployment_steps_new", ["id", "deployment_id", "source_step_id", "position", "name", "status", "started_at", "finished_at", "exit_code", "duration_ms", "error"])
    op.drop_table("deployment_steps")
    op.rename_table("deployment_steps_new", "deployment_steps")
    for name, cols in [
        ("ix_deployment_steps_deployment_id", ["deployment_id"]),
        ("ix_deployment_steps_source_step_id", ["source_step_id"]),
        ("ix_deployment_steps_status", ["status"]),
        ("ix_deployment_steps_deployment_position", ["deployment_id", "position"]),
    ]:
        op.create_index(name, "deployment_steps", cols)

    op.create_table(
        "logs_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deployment_id", sa.Integer()),
        sa.Column("step_id", sa.Integer()),
        sa.Column("stream", sa.String(20)),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["deployment_steps.id"], ondelete="SET NULL"),
    )
    _copy_table("logs", "logs_new", ["id", "deployment_id", "step_id", "stream", "message", "created_at"])
    op.drop_table("logs")
    op.rename_table("logs_new", "logs")
    for name, cols in [
        ("ix_logs_deployment_id", ["deployment_id"]),
        ("ix_logs_step_id", ["step_id"]),
        ("ix_logs_created_at", ["created_at"]),
    ]:
        op.create_index(name, "logs", cols)


def downgrade() -> None:
    raise RuntimeError("SQLite 外键迁移包含数据表重建，禁止自动回滚；请从数据库备份恢复。")
