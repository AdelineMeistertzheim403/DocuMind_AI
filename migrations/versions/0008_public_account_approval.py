"""Public beta review: preserve identities and lifetime admissions; keep signup closed."""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = depends_on = None


def upgrade():
    op.add_column('users', sa.Column('approved_at', sa.DateTime(timezone=True)))
    # Never lower historical admissions, including accounts already removed.
    op.execute("""
        UPDATE public_registration_quota
        SET issued_count = CASE
            WHEN issued_count < (SELECT count(*) FROM users WHERE registration_kind = 'public')
            THEN (SELECT count(*) FROM users WHERE registration_kind = 'public')
            ELSE issued_count END,
            closed = true
        WHERE id = 'public'
    """)


def downgrade():
    bind = op.get_bind()
    if (bind.execute(sa.text("SELECT count(*) FROM users WHERE registration_kind='public'")).scalar()
            or bind.execute(sa.text("SELECT issued_count FROM public_registration_quota WHERE id='public'")).scalar()):
        raise RuntimeError('Downgrade refusé après admission publique : conserver le schéma et la barrière administrative')
    with op.batch_alter_table('users') as batch:
        batch.drop_column('approved_at')
