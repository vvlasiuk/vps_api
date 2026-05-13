from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '08_add_users_column'
down_revision = '07_add_users_column'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'created_at')
