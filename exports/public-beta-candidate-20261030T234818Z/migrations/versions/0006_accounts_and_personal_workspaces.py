"""Keep all owner UUIDs and data; add optional email and personal workspace registry."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('email', sa.String(254), nullable=True))
        batch.add_column(sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint('uq_users_email', ['email'])
    op.create_table('workspaces', sa.Column('owner_id', sa.Uuid(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('workspace_memberships',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('owner_id', sa.Uuid(), sa.ForeignKey('workspaces.owner_id'), unique=True, nullable=False),
        sa.Column('role', sa.String(20), nullable=False))
    # Collect actual owners, never take ownership claims from a browser or environment input.
    op.execute("""INSERT INTO workspaces(owner_id,name,created_at)
        SELECT owner_id,'Espace personnel',CURRENT_TIMESTAMP FROM (
          SELECT owner_id FROM users UNION SELECT owner_id FROM documents
          UNION SELECT owner_id FROM ai_reservations UNION SELECT owner_id FROM ai_usage
          UNION SELECT owner_id FROM ai_summaries UNION SELECT owner_id FROM ai_interactions
          UNION SELECT owner_id FROM chunk_embeddings UNION SELECT owner_id FROM index_jobs
          UNION SELECT owner_id FROM rag_results UNION SELECT owner_id FROM long_summary_jobs
        ) historical""")
    op.execute("INSERT INTO workspace_memberships(user_id,owner_id,role) SELECT id,owner_id,'owner' FROM users")
    op.create_table('account_tokens', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('digest', sa.String(64), unique=True, nullable=False),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('email', sa.String(254), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True)))
    op.create_index('ix_account_tokens_email', 'account_tokens', ['email'])
    op.create_table('account_deletion_requests', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False), sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table('account_deletion_requests')
    op.drop_table('account_tokens')
    op.drop_table('workspace_memberships')
    op.drop_table('workspaces')
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('uq_users_email', type_='unique')
        batch.drop_column('disabled_at')
        batch.drop_column('email')
