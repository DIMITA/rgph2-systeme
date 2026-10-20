"""USSD et SMS : calendrier de passage, badges, préférences de langue, consultations, SMS.

Révision : 0004
Précédente : 0003
Date : 2026-10-20 16:00:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

STATUTS = "statut IN ('brouillon', 'en_revue', 'publie', 'archive')"
TABLES_COEUR = ["preferences_langue", "consultations", "sms"]


def _si_role(role: str, sql: str) -> None:
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
        f"THEN {sql}; END IF; END $$"
    )


def upgrade() -> None:
    op.create_table('calendrier_passages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('territoire_code', sa.String(length=16), nullable=False),
    sa.Column('date_debut', sa.Date(), nullable=False),
    sa.Column('date_fin', sa.Date(), nullable=False),
    sa.Column('statut', sa.String(length=16), server_default='brouillon', nullable=False),
    sa.Column('date_maj', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(STATUTS, name=op.f('ck_calendrier_passages_statut')),
    sa.CheckConstraint('date_fin >= date_debut', name=op.f('ck_calendrier_passages_dates')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_calendrier_passages')),
    )
    op.create_index(op.f('ix_calendrier_passages_territoire_code'), 'calendrier_passages', ['territoire_code'], unique=False)
    op.create_table('badges',
    sa.Column('empreinte', sa.String(length=64), nullable=False),
    sa.Column('territoire_code', sa.String(length=16), nullable=False),
    sa.Column('actif', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('importe_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['territoire_code'], ['coeur.territoires.code'], name=op.f('fk_badges_territoire_code')),
    sa.PrimaryKeyConstraint('empreinte', name=op.f('pk_badges')),
    schema='coeur'
    )
    op.create_index(op.f('ix_badges_territoire_code'), 'badges', ['territoire_code'], unique=False, schema='coeur')
    op.create_table('preferences_langue',
    sa.Column('usager_empreinte', sa.String(length=64), nullable=False),
    sa.Column('langue', sa.String(length=8), nullable=False),
    sa.Column('session_ussd', sa.String(length=100), nullable=True),
    sa.Column('langue_avant', sa.String(length=8), nullable=True),
    sa.Column('maj_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('usager_empreinte', name=op.f('pk_preferences_langue')),
    schema='coeur'
    )
    op.create_index(op.f('ix_preferences_langue_maj_a'), 'preferences_langue', ['maj_a'], unique=False, schema='coeur')
    op.create_table('consultations',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('horodatage', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('canal', sa.String(length=20), nullable=False),
    sa.Column('service', sa.String(length=10), nullable=False),
    sa.Column('resultat', sa.String(length=12), nullable=False),
    sa.Column('langue', sa.String(length=8), nullable=False),
    sa.Column('territoire_code', sa.String(length=16), nullable=True),
    sa.Column('usager_empreinte', sa.String(length=64), nullable=True),
    sa.CheckConstraint("resultat IN ('trouve', 'non_publie', 'valide', 'retire', 'inconnu')", name=op.f('ck_consultations_resultat')),
    sa.CheckConstraint("service IN ('passage', 'badge')", name=op.f('ck_consultations_service')),
    sa.ForeignKeyConstraint(['territoire_code'], ['coeur.territoires.code'], name=op.f('fk_consultations_territoire_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_consultations')),
    schema='coeur'
    )
    op.create_index(op.f('ix_consultations_horodatage'), 'consultations', ['horodatage'], unique=False, schema='coeur')
    op.create_index(op.f('ix_consultations_territoire_code'), 'consultations', ['territoire_code'], unique=False, schema='coeur')
    op.create_table('sms',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('horodatage', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sens', sa.String(length=8), nullable=False),
    sa.Column('usager_empreinte', sa.String(length=64), nullable=False),
    sa.Column('segments', sa.SmallInteger(), server_default='1', nullable=False),
    sa.Column('statut', sa.String(length=8), nullable=False),
    sa.CheckConstraint("sens IN ('entrant', 'sortant')", name=op.f('ck_sms_sens')),
    sa.CheckConstraint("statut IN ('recu', 'envoye', 'echec', 'plafond')", name=op.f('ck_sms_statut')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sms')),
    schema='coeur'
    )
    op.create_index(op.f('ix_sms_horodatage'), 'sms', ['horodatage'], unique=False, schema='coeur')
    op.create_index(op.f('ix_sms_usager_empreinte'), 'sms', ['usager_empreinte'], unique=False, schema='coeur')
    op.add_column('rappels', sa.Column('origine', sa.String(length=8), server_default='appel', nullable=False), schema='coeur')
    op.add_column('rappels', sa.Column('usager_empreinte', sa.String(length=64), nullable=True), schema='coeur')
    op.create_index(op.f('ix_rappels_usager_empreinte'), 'rappels', ['usager_empreinte'], unique=False, schema='coeur')
    op.create_check_constraint(op.f('ck_rappels_origine'), 'rappels',
                               "origine IN ('appel', 'ussd', 'sms')", schema='coeur')

    # Calendrier : administré dans Directus (propriétaire), lu par l'API.
    _si_role("rgph_directus", "ALTER TABLE public.calendrier_passages OWNER TO rgph_directus")
    _si_role("rgph_api", "GRANT SELECT ON public.calendrier_passages TO rgph_api")
    # Badges : remplacés par import (rôle propriétaire) ; l'API les lit et les efface à la purge.
    _si_role("rgph_api", "GRANT SELECT, DELETE ON coeur.badges TO rgph_api")
    coeur = ", ".join(f"coeur.{t}" for t in TABLES_COEUR)
    _si_role("rgph_api", f"GRANT SELECT, INSERT, UPDATE, DELETE ON {coeur} TO rgph_api")
    _si_role("rgph_api", "GRANT USAGE, SELECT ON coeur.consultations_id_seq, coeur.sms_id_seq TO rgph_api")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_rappels_origine'), 'rappels', schema='coeur', type_='check')
    op.drop_index(op.f('ix_rappels_usager_empreinte'), table_name='rappels', schema='coeur')
    op.drop_column('rappels', 'usager_empreinte', schema='coeur')
    op.drop_column('rappels', 'origine', schema='coeur')
    op.drop_index(op.f('ix_sms_usager_empreinte'), table_name='sms', schema='coeur')
    op.drop_index(op.f('ix_sms_horodatage'), table_name='sms', schema='coeur')
    op.drop_table('sms', schema='coeur')
    op.drop_index(op.f('ix_consultations_territoire_code'), table_name='consultations', schema='coeur')
    op.drop_index(op.f('ix_consultations_horodatage'), table_name='consultations', schema='coeur')
    op.drop_table('consultations', schema='coeur')
    op.drop_index(op.f('ix_preferences_langue_maj_a'), table_name='preferences_langue', schema='coeur')
    op.drop_table('preferences_langue', schema='coeur')
    op.drop_index(op.f('ix_badges_territoire_code'), table_name='badges', schema='coeur')
    op.drop_table('badges', schema='coeur')
    op.drop_index(op.f('ix_calendrier_passages_territoire_code'), table_name='calendrier_passages')
    op.drop_table('calendrier_passages')
