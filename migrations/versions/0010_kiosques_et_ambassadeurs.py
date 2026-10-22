"""Kiosques et Ambassadeurs : appareils enrôlés et remontées reçues (anti-doublon)

Révision : 0010
Précédente : 0009
Date : 2026-10-20 14:29:21.041068
"""

import sqlalchemy as sa
from alembic import op


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('appareils',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=12), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('lieu', sa.String(length=120), nullable=True),
    sa.Column('territoire_code', sa.String(length=16), nullable=False),
    sa.Column('langues', sa.String(length=60), nullable=False),
    sa.Column('jeton_empreinte', sa.String(length=64), nullable=True),
    sa.Column('activation_empreinte', sa.String(length=64), nullable=True),
    sa.Column('activation_expire_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cree_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('active_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoque_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('derniere_synchro_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version_paquet', sa.String(length=64), nullable=True),
    sa.CheckConstraint("type IN ('kiosque', 'ambassadeur')", name=op.f('ck_appareils_type')),
    sa.ForeignKeyConstraint(['territoire_code'], ['coeur.territoires.code'], name=op.f('fk_appareils_territoire_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appareils')),
    sa.UniqueConstraint('activation_empreinte', name=op.f('uq_appareils_activation_empreinte')),
    sa.UniqueConstraint('code', name=op.f('uq_appareils_code')),
    sa.UniqueConstraint('jeton_empreinte', name=op.f('uq_appareils_jeton_empreinte')),
    schema='coeur'
    )
    op.create_index(op.f('ix_appareils_territoire_code'), 'appareils', ['territoire_code'], unique=False, schema='coeur')
    op.create_table('remontees_terrain',
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('appareil_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('recu_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['appareil_id'], ['coeur.appareils.id'], name=op.f('fk_remontees_terrain_appareil_id'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_remontees_terrain')),
    schema='coeur'
    )
    op.create_index(op.f('ix_remontees_terrain_appareil_id'), 'remontees_terrain', ['appareil_id'], unique=False, schema='coeur')
    op.create_index(op.f('ix_remontees_terrain_recu_a'), 'remontees_terrain', ['recu_a'], unique=False, schema='coeur')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rgph_api') THEN "
               "GRANT SELECT, INSERT, UPDATE, DELETE ON coeur.appareils, coeur.remontees_terrain "
               "TO rgph_api; GRANT USAGE, SELECT ON coeur.appareils_id_seq TO rgph_api; "
               "END IF; END $$")


def downgrade() -> None:
    op.drop_index(op.f('ix_remontees_terrain_recu_a'), table_name='remontees_terrain', schema='coeur')
    op.drop_index(op.f('ix_remontees_terrain_appareil_id'), table_name='remontees_terrain', schema='coeur')
    op.drop_table('remontees_terrain', schema='coeur')
    op.drop_index(op.f('ix_appareils_territoire_code'), table_name='appareils', schema='coeur')
    op.drop_table('appareils', schema='coeur')
