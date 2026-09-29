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
    bind = op.get_bind()
    orphan_checks = [
        ("steps.project_id", "SELECT COUNT(*) FROM steps s LEFT JOIN projects p ON p.id = s.project_id WHERE s.project_id IS NOT NULL AND p.id IS NULL"),
        ("envs.project_id", "SELECT COUNT(*) FROM envs e LEFT JOIN projects p ON p.id = e.project_id WHERE e.project_id IS NOT NULL AND p.id IS NULL"),
        ("deployments.project_id", "SELECT COUNT(*) FROM deployments d LEFT JOIN projects p ON p.id = d.project_id WHERE d.project_id IS NOT NULL AND p.id IS NULL"),
        ("deployments.user_id", "SELECT COUNT(*) FROM deployments d LEFT JOIN users u ON u.id = d.user_id WHERE d.user_id IS NOT NULL AND u.id IS NULL"),
        ("deployments.retry_of", "SELECT COUNT(*) FROM deployments d LEFT JOIN deployments parent ON parent.id = d.retry_of WHERE d.retry_of IS NOT NULL AND parent.id IS NULL"),
        ("deployment_steps.deployment_id", "SELECT COUNT(*) FROM deployment_steps s LEFT JOIN deployments d ON d.id = s.deployment_id WHERE s.deployment_id IS NOT NULL AND d.id IS NULL"),
        ("deployment_steps.source_step_id", "SELECT COUNT(*) FROM deployment_steps s LEFT JOIN steps x ON x.id = s.source_step_id WHERE s.source_step_id IS NOT NULL AND x.id IS NULL"),
        ("logs.deployment_id", "SELECT COUNT(*) FROM logs l LEFT JOIN deployments d ON d.id = l.deployment_id WHERE l.deployment_id IS NOT NULL AND d.id IS NULL"),
        ("logs.step_id", "SELECT COUNT(*) FROM logs l LEFT JOIN deployment_steps s ON s.id = l.step_id WHERE l.step_id IS NOT NULL AND s.id IS NULL"),
    ]
    for name, query in orphan_checks:
        if bind.execute(sa.text(query)).scalar_one():
            raise RuntimeError(f"数据库存在孤立外键数据: {name}，请先修复数据后再执行 Migration。")

    # SQLite requires child tables to be removed before their parent tables
    # when foreign_keys=ON. Build the complete replacement schema first.
    op.create_table("users_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("role", sa.String(20)),
        sa.UniqueConstraint("username"))
    op.create_table("projects_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200)),
        sa.Column("description", sa.Text()),
        sa.Column("branch", sa.String(255)),
        sa.Column("shell", sa.String(20)),
        sa.Column("enabled", sa.Boolean()))
    op.create_table("steps_new",
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
        sa.ForeignKeyConstraint(["project_id"], ["projects_new.id"], ondelete="CASCADE"))
    op.create_table("envs_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer()),
        sa.Column("key", sa.String(255)),
        sa.Column("value", sa.Text()),
        sa.Column("is_secret", sa.Boolean()),
        sa.ForeignKeyConstraint(["project_id"], ["projects_new.id"], ondelete="CASCADE"))
    op.create_table("deployments_new",
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
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("before_sha", sa.String(64)),
        sa.Column("after_sha", sa.String(64)),
        sa.Column("retry_of", sa.Integer()),
        sa.ForeignKeyConstraint(["project_id"], ["projects_new.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users_new.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["retry_of"], ["deployments_new.id"], ondelete="SET NULL"))
    op.create_table("deployment_steps_new",
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
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments_new.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_step_id"], ["steps_new.id"], ondelete="SET NULL"))
    op.create_table("logs_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deployment_id", sa.Integer()),
        sa.Column("step_id", sa.Integer()),
        sa.Column("stream", sa.String(20)),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments_new.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["deployment_steps_new.id"], ondelete="SET NULL"))

    _copy_table("users", "users_new", ["id", "username", "password_hash", "role"])
    _copy_table("projects", "projects_new", ["id", "name", "description", "branch", "shell", "enabled"])
    _copy_table("steps", "steps_new", ["id", "project_id", "name", "step_type", "cwd", "command", "enabled", "timeout", "continue_on_error", "position"])
    _copy_table("envs", "envs_new", ["id", "project_id", "key", "value", "is_secret"])
    _copy_table("deployments", "deployments_new", ["id", "project_id", "user_id", "status", "exit_code", "created_at", "started_at", "finished_at", "config_snapshot", "note", "cancel_requested", "state_version", "before_sha", "after_sha", "retry_of"])
    _copy_table("deployment_steps", "deployment_steps_new", ["id", "deployment_id", "source_step_id", "position", "name", "status", "started_at", "finished_at", "exit_code", "duration_ms", "error"])
    _copy_table("logs", "logs_new", ["id", "deployment_id", "step_id", "stream", "message", "created_at"])

    for table in ["logs", "deployment_steps", "deployments", "envs", "steps", "projects", "users"]:
        op.drop_table(table)

    for old, new in [
        ("users_new", "users"),
        ("projects_new", "projects"),
        ("steps_new", "steps"),
        ("envs_new", "envs"),
        ("deployments_new", "deployments"),
        ("deployment_steps_new", "deployment_steps"),
        ("logs_new", "logs"),
    ]:
        op.rename_table(old, new)

    for name, table, cols in [
        ("ix_deployments_project_id","deployments",["project_id"]),
        ("ix_deployments_user_id","deployments",["user_id"]),
        ("ix_deployments_status","deployments",["status"]),
        ("ix_deployments_created_at","deployments",["created_at"]),
        ("ix_deployments_cancel_requested","deployments",["cancel_requested"]),
        ("ix_deployments_project_created","deployments",["project_id","created_at"]),
        ("ix_deployments_status_created","deployments",["status","created_at"]),
        ("ix_deployment_steps_deployment_id","deployment_steps",["deployment_id"]),
        ("ix_deployment_steps_source_step_id","deployment_steps",["source_step_id"]),
        ("ix_deployment_steps_status","deployment_steps",["status"]),
        ("ix_deployment_steps_deployment_position","deployment_steps",["deployment_id","position"]),
        ("ix_logs_deployment_id","logs",["deployment_id"]),
        ("ix_logs_step_id","logs",["step_id"]),
        ("ix_logs_created_at","logs",["created_at"]),
    ]:
        op.create_index(name, table, cols)


def downgrade() -> None:
    raise RuntimeError("SQLite 外键迁移包含数据表重建，禁止自动回滚；请从数据库备份恢复。")
