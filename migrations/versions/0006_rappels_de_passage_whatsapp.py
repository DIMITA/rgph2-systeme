"""WhatsApp : abonnements aux rappels de passage (numéro chiffré)

Révision : 0006
Précédente : 0005
Date : 2026-10-20 15:45:15.560053
"""

import sqlalchemy as sa
from alembic import op


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('abonnements_whatsapp',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('usager_empreinte', sa.String(length=64), nullable=False),
    sa.Column('numero_chiffre', sa.Text(), nullable=False),
    sa.Column('territoire_code', sa.String(length=16), nullable=False),
    sa.Column('langue', sa.String(length=8), nullable=False),
    sa.Column('cree_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('envoyes', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['territoire_code'], ['coeur.territoires.code'], name=op.f('fk_abonnements_whatsapp_territoire_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_abonnements_whatsapp')),
    sa.UniqueConstraint('usager_empreinte', 'territoire_code', name='uq_abonnements_whatsapp_usager_territoire'),
    schema='coeur'
    )
    op.create_index(op.f('ix_abonnements_whatsapp_cree_a'), 'abonnements_whatsapp', ['cree_a'], unique=False, schema='coeur')
    op.create_index(op.f('ix_abonnements_whatsapp_territoire_code'), 'abonnements_whatsapp', ['territoire_code'], unique=False, schema='coeur')
    op.create_index(op.f('ix_abonnements_whatsapp_usager_empreinte'), 'abonnements_whatsapp', ['usager_empreinte'], unique=False, schema='coeur')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rgph_api') THEN "
               "GRANT SELECT, INSERT, UPDATE, DELETE ON coeur.abonnements_whatsapp TO rgph_api; "
               "GRANT USAGE, SELECT ON coeur.abonnements_whatsapp_id_seq TO rgph_api; END IF; END $$")


def downgrade() -> None:
    op.drop_index(op.f('ix_abonnements_whatsapp_usager_empreinte'), table_name='abonnements_whatsapp', schema='coeur')
    op.drop_index(op.f('ix_abonnements_whatsapp_territoire_code'), table_name='abonnements_whatsapp', schema='coeur')
    op.drop_index(op.f('ix_abonnements_whatsapp_cree_a'), table_name='abonnements_whatsapp', schema='coeur')
    op.drop_table('abonnements_whatsapp', schema='coeur')
