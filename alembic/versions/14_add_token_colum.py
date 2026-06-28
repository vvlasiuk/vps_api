from alembic import op
import sqlalchemy as sa

revision = '14_add_token_column'
down_revision = '13_add_password_to_users'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('tokens', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_tokens_user_id', 'tokens', 'users', ['user_id'], ['id'])

def downgrade():
    op.drop_constraint('fk_tokens_user_id', 'tokens', type_='foreignkey')
    op.drop_column('tokens', 'user_id')