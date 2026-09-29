"""add project deployment members"""
from alembic import op
import sqlalchemy as sa

revision = "0004_project_members"
down_revision = "0003_deployment_state_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "project_members" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "project_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
        op.create_index("ix_project_members_user_id", "project_members", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "project_members" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_project_members_user_id", table_name="project_members")
        op.drop_index("ix_project_members_project_id", table_name="project_members")
        op.drop_table("project_members")
