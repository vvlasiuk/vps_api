from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '04_add_end_at_to_context'
down_revision = '03bd65e9fc8c'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('context', sa.Column('end_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('context', 'end_at')