from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '12_global_msg_tables'
down_revision = '11_global_msg_tables'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('global_message_telegram') as batch_op:
        batch_op.alter_column(
            'chat_id',
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            nullable=True
        )

def downgrade():
    with op.batch_alter_table('global_message_telegram') as batch_op:
        batch_op.alter_column(
            'chat_id',
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            nullable=True
        )