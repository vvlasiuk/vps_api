from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '10_add_global_msg_tables'
down_revision = '09_drop_unique_context_object_id'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'global_message_context',
        sa.Column('global_msg_id', sa.Integer(), primary_key=True),
        sa.Column('context_id', sa.Integer(), nullable=False)
    )
    op.create_table(
        'global_message_telegram',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('global_msg_id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False)
    )

def downgrade():
    op.drop_table('global_message_telegram')
    op.drop_table('global_message_context')