from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '07_add_users_column'
down_revision = '06_add_users'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('chat_id', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('role', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('username', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('users', 'chat_id')
    op.drop_column('users', 'role')
    op.drop_column('users', 'username')