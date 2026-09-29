"""initial schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("username", sa.String(100), nullable=True), sa.Column("password_hash", sa.String(255), nullable=True), sa.Column("role", sa.String(20), nullable=True), sa.UniqueConstraint("username"))
    op.create_table("projects", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(200)), sa.Column("description", sa.Text()), sa.Column("branch", sa.String(255)), sa.Column("shell", sa.String(20)), sa.Column("enabled", sa.Boolean()))
    op.create_table("steps", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("project_id", sa.Integer()), sa.Column("name", sa.String(200)), sa.Column("step_type", sa.String(30)), sa.Column("cwd", sa.String(1000)), sa.Column("command", sa.Text()), sa.Column("enabled", sa.Boolean()), sa.Column("timeout", sa.Integer()), sa.Column("continue_on_error", sa.Boolean()), sa.Column("position", sa.Integer()), sa.ForeignKeyConstraint(["project_id"], ["projects.id"]))
    op.create_table("envs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("project_id", sa.Integer()), sa.Column("key", sa.String(255)), sa.Column("value", sa.Text()), sa.Column("is_secret", sa.Boolean()), sa.ForeignKeyConstraint(["project_id"], ["projects.id"]))
    op.create_table("deployments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("project_id", sa.Integer()), sa.Column("user_id", sa.Integer()), sa.Column("status", sa.String(30)), sa.Column("exit_code", sa.Integer()), sa.Column("created_at", sa.DateTime()), sa.Column("started_at", sa.DateTime()), sa.Column("finished_at", sa.DateTime()), sa.Column("config_snapshot", sa.Text()), sa.Column("note", sa.Text()), sa.Column("cancel_requested", sa.Boolean()), sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"), sa.Column("before_sha", sa.String(64)), sa.Column("after_sha", sa.String(64)), sa.Column("retry_of", sa.Integer()))
    op.create_index("ix_deployments_project_id","deployments",["project_id"])
    op.create_index("ix_deployments_user_id","deployments",["user_id"])
    op.create_index("ix_deployments_status","deployments",["status"])
    op.create_index("ix_deployments_created_at","deployments",["created_at"])
    op.create_index("ix_deployments_cancel_requested","deployments",["cancel_requested"])
    op.create_index("ix_deployments_project_created","deployments",["project_id","created_at"])
    op.create_index("ix_deployments_status_created","deployments",["status","created_at"])
    op.create_table("deployment_steps", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("deployment_id", sa.Integer()), sa.Column("source_step_id", sa.Integer()), sa.Column("position", sa.Integer()), sa.Column("name", sa.String(200)), sa.Column("status", sa.String(30)), sa.Column("started_at", sa.DateTime()), sa.Column("finished_at", sa.DateTime()), sa.Column("exit_code", sa.Integer()), sa.Column("duration_ms", sa.Integer()), sa.Column("error", sa.Text()), sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"]))
    op.create_index("ix_deployment_steps_deployment_id","deployment_steps",["deployment_id"])
    op.create_index("ix_deployment_steps_source_step_id","deployment_steps",["source_step_id"])
    op.create_index("ix_deployment_steps_status","deployment_steps",["status"])
    op.create_index("ix_deployment_steps_deployment_position","deployment_steps",["deployment_id","position"])
    op.create_table("logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("deployment_id", sa.Integer()), sa.Column("step_id", sa.Integer()), sa.Column("stream", sa.String(20)), sa.Column("message", sa.Text()), sa.Column("created_at", sa.DateTime()))
    op.create_index("ix_logs_deployment_id","logs",["deployment_id"])
    op.create_index("ix_logs_step_id","logs",["step_id"])
    op.create_index("ix_logs_created_at","logs",["created_at"])

def downgrade() -> None:
    op.drop_table("logs")
    op.drop_table("deployment_steps")
    op.drop_table("deployments")
    op.drop_table("envs")
    op.drop_table("steps")
    op.drop_table("projects")
    op.drop_table("users")
