from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '06_add_users'
down_revision = '05_add_closed'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('lastname', sa.String(length=255), nullable=True),
        sa.Column('firstname', sa.String(length=255), nullable=True),
        sa.Column('middlename', sa.String(length=255), nullable=True),
        sa.Column('position', sa.String(length=255), nullable=True),
        sa.Column('department', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_table('users')