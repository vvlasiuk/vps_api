from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '11_global_msg_tables'
down_revision = '10_add_global_msg_tables'
branch_labels = None
depends_on = None

def upgrade():
    # Оновлення global_message_context
    with op.batch_alter_table('global_message_context') as batch_op:
        batch_op.alter_column('global_msg_id',
                              existing_type=sa.Integer(),
                              autoincrement=True,
                              existing_nullable=False)
        batch_op.alter_column('context_id',
                              existing_type=sa.Integer(),
                              nullable=True)

    # Оновлення global_message_telegram
    with op.batch_alter_table('global_message_telegram') as batch_op:
        batch_op.alter_column('chat_id',
                              existing_type=sa.Integer(),
                              nullable=True)
        batch_op.alter_column('message_id',
                              existing_type=sa.Integer(),
                              nullable=True)

def downgrade():
    # Повернення до попереднього стану (опціонально)
    with op.batch_alter_table('global_message_context') as batch_op:
        batch_op.alter_column('global_msg_id',
                              existing_type=sa.Integer(),
                              autoincrement=False,
                              existing_nullable=False)
        batch_op.alter_column('context_id',
                              existing_type=sa.Integer(),
                              nullable=False)

    with op.batch_alter_table('global_message_telegram') as batch_op:
        batch_op.alter_column('chat_id',
                              existing_type=sa.Integer(),
                              nullable=False)
        batch_op.alter_column('message_id',
                              existing_type=sa.Integer(),
                              nullable=False)
