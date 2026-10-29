"""Public beta: additive fields, historical identities unchanged, persistent admission cap."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('registration_kind', sa.String(16), nullable=False, server_default='legacy'))
        batch.add_column(sa.Column('email_verified_at', sa.DateTime(timezone=True)))
        batch.add_column(sa.Column('terms_version', sa.String(40)))
        batch.add_column(sa.Column('terms_accepted_at', sa.DateTime(timezone=True)))
    op.create_table('public_registration_quota',
                    sa.Column('id', sa.String(16), primary_key=True),
                    sa.Column('issued_count', sa.BigInteger(), nullable=False, server_default='0'),
                    sa.Column('closed', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("INSERT INTO public_registration_quota(id,issued_count) VALUES ('public',0)")


def downgrade():
    bind=op.get_bind()
    if (bind.execute(sa.text("SELECT issued_count FROM public_registration_quota WHERE id='public'")).scalar() or
            bind.execute(sa.text("SELECT count(*) FROM users WHERE registration_kind='public'")).scalar()):
        raise RuntimeError('Downgrade refusé après admission publique : revue et sauvegarde nécessaires')
    op.drop_table('public_registration_quota')
    with op.batch_alter_table('users') as batch:
        for name in ('terms_accepted_at','terms_version','email_verified_at','registration_kind'):
            batch.drop_column(name)
