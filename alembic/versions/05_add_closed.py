from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '05_add_closed'
down_revision = '04_add_end_at_to_context'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('context', sa.Column('closed', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.drop_column('context', 'status')

def downgrade():
    op.add_column('context', sa.Column('status', sa.String(length=50), nullable=True))
    op.drop_column('context', 'closed')