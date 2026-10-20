"""Console des agents : qualification des appels, rappel « en cours », journal des écoutes.

Révision : 0003
Précédente : 0002
Date : 2026-10-20 11:34:47.889743
"""

import sqlalchemy as sa
from alembic import op


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

QUALIFICATIONS = "('renseigne', 'signalement', 'transmis_bcr', 'hors_sujet', 'coupe')"
STATUTS_AVANT = "('a_rappeler', 'rappele', 'injoignable', 'expire')"
STATUTS_APRES = "('a_rappeler', 'en_cours', 'rappele', 'injoignable', 'expire')"


def _si_role(role: str, sql: str) -> None:
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
        f"THEN {sql}; END IF; END $$"
    )


def upgrade() -> None:
    op.create_table('ecoutes',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('enregistrement_id', sa.BigInteger(), nullable=True),
    sa.Column('fichier', sa.String(length=255), nullable=False),
    sa.Column('utilisateur', sa.String(length=255), nullable=False),
    sa.Column('ecoute_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['enregistrement_id'], ['coeur.enregistrements.id'], name=op.f('fk_ecoutes_enregistrement_id'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ecoutes')),
    schema='coeur'
    )
    op.create_index(op.f('ix_ecoutes_enregistrement_id'), 'ecoutes', ['enregistrement_id'], unique=False, schema='coeur')
    op.add_column('appels', sa.Column('qualification', sa.String(length=20), nullable=True), schema='coeur')
    op.create_check_constraint(op.f('ck_appels_qualification'), 'appels',
                               f'qualification IN {QUALIFICATIONS}', schema='coeur')
    op.drop_constraint(op.f('ck_rappels_statut'), 'rappels', schema='coeur', type_='check')
    op.create_check_constraint(op.f('ck_rappels_statut'), 'rappels',
                               f'statut IN {STATUTS_APRES}', schema='coeur')
    _si_role("rgph_api", "GRANT SELECT, INSERT, UPDATE, DELETE ON coeur.ecoutes TO rgph_api")
    _si_role("rgph_api", "GRANT USAGE, SELECT ON coeur.ecoutes_id_seq TO rgph_api")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_rappels_statut'), 'rappels', schema='coeur', type_='check')
    op.execute("UPDATE coeur.rappels SET statut = 'a_rappeler' WHERE statut = 'en_cours'")
    op.create_check_constraint(op.f('ck_rappels_statut'), 'rappels',
                               f'statut IN {STATUTS_AVANT}', schema='coeur')
    op.drop_constraint(op.f('ck_appels_qualification'), 'appels', schema='coeur', type_='check')
    op.drop_column('appels', 'qualification', schema='coeur')
    op.drop_index(op.f('ix_ecoutes_enregistrement_id'), table_name='ecoutes', schema='coeur')
    op.drop_table('ecoutes', schema='coeur')
