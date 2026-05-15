from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "09_drop_unique_context_object_id"
down_revision = "08_add_users_column"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT INDEX_NAME
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'context'
              AND COLUMN_NAME = 'object_id'
              AND NON_UNIQUE = 0
            LIMIT 1
            """
        )
    ).fetchone()

    if row:
        op.drop_index(row[0], table_name="context")


def downgrade():
    op.create_unique_constraint(
        "uq_context_object_id",
        "context",
        ["object_id"],
    )
