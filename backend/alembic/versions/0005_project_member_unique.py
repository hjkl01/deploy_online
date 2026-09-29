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

    bind.execute(sa.text(
        """
        DELETE FROM project_members
        WHERE user_id IN (
            SELECT id FROM users WHERE role != 'operator'
        )
        """
    ))

    member_count = bind.execute(sa.text("SELECT COUNT(*) FROM project_members")).scalar_one()
    if member_count == 0:
        bind.execute(sa.text(
            """
            INSERT INTO project_members (project_id, user_id)
            SELECT p.id, u.id
            FROM projects p
            CROSS JOIN users u
            WHERE u.role = 'operator'
            """
        ))

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

    indexes = inspector.get_indexes("project_members")
    if not any(i.get("name") == "uq_project_members_project_user" and i.get("unique") for i in indexes):
        op.create_index(
            "uq_project_members_project_user",
            "project_members",
            ["project_id", "user_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "project_members" in sa.inspect(bind).get_table_names():
        indexes = sa.inspect(bind).get_indexes("project_members")
        if any(i.get("name") == "uq_project_members_project_user" for i in indexes):
            op.drop_index("uq_project_members_project_user", table_name="project_members")
