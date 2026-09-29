"""enforce unique project deployment members"""
from alembic import op
import sqlalchemy as sa


revision = "0005_project_member_unique"
down_revision = "0004_project_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_members" not in inspector.get_table_names():
        return

    duplicates = bind.execute(sa.text(
        """
        SELECT project_id, user_id, MIN(id) AS keep_id
        FROM project_members
        GROUP BY project_id, user_id
        HAVING COUNT(*) > 1
        """
    )).fetchall()
    for project_id, user_id, keep_id in duplicates:
        bind.execute(
            sa.text(
                "DELETE FROM project_members "
                "WHERE project_id = :project_id AND user_id = :user_id AND id != :keep_id"
            ),
            {"project_id": project_id, "user_id": user_id, "keep_id": keep_id},
        )

    constraints = inspector.get_unique_constraints("project_members")
    if not any(set(c.get("column_names", [])) == {"project_id", "user_id"} for c in constraints):
        op.create_unique_constraint(
            "uq_project_members_project_user",
            "project_members",
            ["project_id", "user_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "project_members" in sa.inspect(bind).get_table_names():
        try:
            op.drop_constraint(
                "uq_project_members_project_user",
                "project_members",
                type_="unique",
            )
        except Exception:
            pass
