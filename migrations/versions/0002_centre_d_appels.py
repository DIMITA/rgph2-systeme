"""Centre d'appels : appels, rappels, enregistrements ; position des contenus dans le SVI.

Révision : 0002
Précédente : 0001
Date : 2026-10-20 11:07:04.385322
"""

import sqlalchemy as sa
from alembic import op


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

TABLES = ["appels", "rappels", "enregistrements"]


def _si_role(role: str, sql: str) -> None:
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
        f"THEN {sql}; END IF; END $$"
    )


def upgrade() -> None:
    op.create_table('appels',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('reference', sa.String(length=64), nullable=False),
    sa.Column('debut', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('langue', sa.String(length=8), nullable=True),
    sa.Column('usager_empreinte', sa.String(length=64), nullable=True),
    sa.Column('entree_file_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decroche_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('poste', sa.String(length=32), nullable=True),
    sa.Column('fin_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rappel_demande', sa.Boolean(), server_default='false', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appels')),
    sa.UniqueConstraint('reference', name=op.f('uq_appels_reference')),
    schema='coeur'
    )
    op.create_index(op.f('ix_appels_debut'), 'appels', ['debut'], unique=False, schema='coeur')
    op.create_table('enregistrements',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('cree_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('appel_reference', sa.String(length=64), nullable=False),
    sa.Column('fichier', sa.String(length=255), nullable=False),
    sa.Column('poste', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_enregistrements')),
    sa.UniqueConstraint('fichier', name=op.f('uq_enregistrements_fichier')),
    schema='coeur'
    )
    op.create_index(op.f('ix_enregistrements_appel_reference'), 'enregistrements', ['appel_reference'], unique=False, schema='coeur')
    op.create_index(op.f('ix_enregistrements_cree_a'), 'enregistrements', ['cree_a'], unique=False, schema='coeur')
    op.create_table('rappels',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('cree_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('appel_reference', sa.String(length=64), nullable=False),
    sa.Column('numero_chiffre', sa.Text(), nullable=True),
    sa.Column('langue', sa.String(length=8), nullable=True),
    sa.Column('statut', sa.String(length=16), server_default='a_rappeler', nullable=False),
    sa.Column('traite_a', sa.DateTime(timezone=True), nullable=True),
    sa.Column('traite_par', sa.String(length=255), nullable=True),
    sa.CheckConstraint("statut IN ('a_rappeler', 'rappele', 'injoignable', 'expire')", name=op.f('ck_rappels_statut')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rappels')),
    schema='coeur'
    )
    op.create_index(op.f('ix_rappels_cree_a'), 'rappels', ['cree_a'], unique=False, schema='coeur')
    op.add_column('contenus', sa.Column('ordre_svi', sa.Integer(), nullable=True))
    op.add_column('contenus_traductions', sa.Column('audio_question_url', sa.String(length=500), nullable=True))
    op.create_check_constraint(op.f('ck_contenus_ordre_svi'), 'contenus', 'ordre_svi BETWEEN 1 AND 8')

    tables = ", ".join(f"coeur.{t}" for t in TABLES)
    sequences = ", ".join(f"coeur.{t}_id_seq" for t in TABLES)
    _si_role("rgph_api", f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO rgph_api")
    _si_role("rgph_api", f"GRANT USAGE, SELECT ON {sequences} TO rgph_api")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_contenus_ordre_svi'), 'contenus', type_='check')
    op.drop_column('contenus_traductions', 'audio_question_url')
    op.drop_column('contenus', 'ordre_svi')
    op.drop_index(op.f('ix_rappels_cree_a'), table_name='rappels', schema='coeur')
    op.drop_table('rappels', schema='coeur')
    op.drop_index(op.f('ix_enregistrements_cree_a'), table_name='enregistrements', schema='coeur')
    op.drop_index(op.f('ix_enregistrements_appel_reference'), table_name='enregistrements', schema='coeur')
    op.drop_table('enregistrements', schema='coeur')
    op.drop_index(op.f('ix_appels_debut'), table_name='appels', schema='coeur')
    op.drop_table('appels', schema='coeur')
