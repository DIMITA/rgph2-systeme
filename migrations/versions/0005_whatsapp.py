"""WhatsApp : conversations en attente, journal des messages, vidéo des contenus, rappels.

Révision : 0005
Précédente : 0004
Date : 2026-10-20 15:36:55.514638
"""

import sqlalchemy as sa
from alembic import op


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

ORIGINES_AVANT = "origine IN ('appel', 'ussd', 'sms')"
ORIGINES_APRES = "origine IN ('appel', 'ussd', 'sms', 'whatsapp')"


def _si_role(role: str, sql: str) -> None:
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
        f"THEN {sql}; END IF; END $$"
    )


def upgrade() -> None:
    op.create_table('conversations_whatsapp',
    sa.Column('usager_empreinte', sa.String(length=64), nullable=False),
    sa.Column('attente', sa.String(length=20), nullable=True),
    sa.Column('contexte', sa.JSON(), nullable=False),
    sa.Column('maj_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('usager_empreinte', name=op.f('pk_conversations_whatsapp')),
    schema='coeur'
    )
    op.create_index(op.f('ix_conversations_whatsapp_maj_a'), 'conversations_whatsapp', ['maj_a'], unique=False, schema='coeur')
    op.create_table('whatsapp_messages',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('horodatage', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sens', sa.String(length=8), nullable=False),
    sa.Column('usager_empreinte', sa.String(length=64), nullable=False),
    sa.Column('categorie', sa.String(length=8), server_default='service', nullable=False),
    sa.Column('statut', sa.String(length=8), nullable=False),
    sa.CheckConstraint("categorie IN ('service', 'modele')", name=op.f('ck_whatsapp_messages_categorie')),
    sa.CheckConstraint("sens IN ('entrant', 'sortant')", name=op.f('ck_whatsapp_messages_sens')),
    sa.CheckConstraint("statut IN ('recu', 'envoye', 'echec')", name=op.f('ck_whatsapp_messages_statut')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_whatsapp_messages')),
    schema='coeur'
    )
    op.create_index(op.f('ix_whatsapp_messages_horodatage'), 'whatsapp_messages', ['horodatage'], unique=False, schema='coeur')
    op.create_index(op.f('ix_whatsapp_messages_usager_empreinte'), 'whatsapp_messages', ['usager_empreinte'], unique=False, schema='coeur')
    op.add_column('contenus_traductions', sa.Column('video_url', sa.String(length=500), nullable=True))
    op.drop_constraint(op.f('ck_rappels_origine'), 'rappels', schema='coeur', type_='check')
    op.create_check_constraint(op.f('ck_rappels_origine'), 'rappels', ORIGINES_APRES, schema='coeur')

    _si_role("rgph_api", "GRANT SELECT, INSERT, UPDATE, DELETE ON coeur.conversations_whatsapp, "
                         "coeur.whatsapp_messages TO rgph_api")
    _si_role("rgph_api", "GRANT USAGE, SELECT ON coeur.whatsapp_messages_id_seq TO rgph_api")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_rappels_origine'), 'rappels', schema='coeur', type_='check')
    op.execute("DELETE FROM coeur.rappels WHERE origine = 'whatsapp'")
    op.create_check_constraint(op.f('ck_rappels_origine'), 'rappels', ORIGINES_AVANT, schema='coeur')
    op.drop_column('contenus_traductions', 'video_url')
    op.drop_index(op.f('ix_whatsapp_messages_usager_empreinte'), table_name='whatsapp_messages', schema='coeur')
    op.drop_index(op.f('ix_whatsapp_messages_horodatage'), table_name='whatsapp_messages', schema='coeur')
    op.drop_table('whatsapp_messages', schema='coeur')
    op.drop_index(op.f('ix_conversations_whatsapp_maj_a'), table_name='conversations_whatsapp', schema='coeur')
    op.drop_table('conversations_whatsapp', schema='coeur')
