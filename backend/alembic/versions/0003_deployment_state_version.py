"""add deployment state version"""
from alembic import op
import sqlalchemy as sa


revision = "0003_deployment_state_version"
down_revision = "0002_foreign_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("deployments")}
    if "state_version" not in columns:
        op.add_column(
            "deployments",
            sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("deployments")}
    if "state_version" in columns:
        op.drop_column("deployments", "state_version")
