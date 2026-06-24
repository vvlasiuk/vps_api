from alembic import op
import sqlalchemy as sa

revision = '13_add_password_to_users'
down_revision = '12_global_msg_tables'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('password', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')))

def downgrade():
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'password')