"""Schéma initial : contenus du CMS (public), territoires, interactions, signalements (coeur).

Révision : 0001
Précédente : 
Date : 2026-10-20 10:12:41.325792
"""

import sqlalchemy as sa
from alembic import op


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

TABLES_CMS = ["langues", "contenus", "contenus_traductions", "formulations"]
TABLES_REFERENTIEL = ["provinces", "territoires"]
TABLES_COEUR = ["interactions", "signalements"]

LANGUES_INITIALES = [
    {"code": "fr", "nom": "Français", "active": True},
    {"code": "ln", "nom": "Lingala", "active": True},
    {"code": "sw", "nom": "Kiswahili", "active": True},
    {"code": "kg", "nom": "Kikongo", "active": True},
    {"code": "lua", "nom": "Tshiluba", "active": True},
]


def _si_role(role: str, sql: str) -> None:
    """Accorde des droits seulement si le rôle existe (créé par db/init/01-roles.sh)."""
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') "
        f"THEN {sql}; END IF; END $$"
    )


def _droits() -> None:
    cms = ", ".join(f"public.{t}" for t in TABLES_CMS)
    referentiel = ", ".join(f"coeur.{t}" for t in TABLES_REFERENTIEL)
    coeur = ", ".join(f"coeur.{t}" for t in TABLES_COEUR)
    sequences_coeur = ", ".join(f"coeur.{t}_id_seq" for t in TABLES_COEUR)

    # Directus : propriétaire des tables de contenus (il en a besoin pour gérer
    # les relations dans son interface), ne voit rien du schéma coeur.
    for table in TABLES_CMS:
        _si_role("rgph_directus", f"ALTER TABLE public.{table} OWNER TO rgph_directus")
    # API : lecture seule sur les contenus et le référentiel, écriture dans son journal.
    _si_role("rgph_api", f"GRANT SELECT ON {cms}, {referentiel} TO rgph_api")
    _si_role("rgph_api", f"GRANT SELECT, INSERT, UPDATE, DELETE ON {coeur} TO rgph_api")
    _si_role("rgph_api", f"GRANT USAGE, SELECT ON {sequences_coeur} TO rgph_api")


def upgrade() -> None:
    op.create_table('provinces',
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('nom', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_provinces')),
    schema='coeur'
    )
    op.create_table('contenus',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cle', sa.String(length=100), nullable=False),
    sa.Column('categorie', sa.String(length=50), server_default='general', nullable=False),
    sa.Column('statut', sa.String(length=16), server_default='brouillon', nullable=False),
    sa.Column('date_creation', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('date_maj', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("statut IN ('brouillon', 'en_revue', 'publie', 'archive')", name=op.f('ck_contenus_statut')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contenus')),
    sa.UniqueConstraint('cle', name=op.f('uq_contenus_cle')),
    )
    op.create_table('langues',
    sa.Column('code', sa.String(length=8), nullable=False),
    sa.Column('nom', sa.String(length=64), nullable=False),
    sa.Column('active', sa.Boolean(), server_default='true', nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_langues')),
    )
    op.create_table('territoires',
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('nom', sa.String(length=100), nullable=False),
    sa.Column('type', sa.String(length=16), nullable=False),
    sa.Column('province_code', sa.String(length=16), nullable=False),
    sa.CheckConstraint("type IN ('territoire', 'ville')", name=op.f('ck_territoires_type')),
    sa.ForeignKeyConstraint(['province_code'], ['coeur.provinces.code'], name=op.f('fk_territoires_province_code')),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_territoires')),
    schema='coeur'
    )
    op.create_index(op.f('ix_territoires_province_code'), 'territoires', ['province_code'], unique=False, schema='coeur')
    op.create_table('contenus_traductions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('contenu_id', sa.Integer(), nullable=False),
    sa.Column('langue_code', sa.String(length=8), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('reponse', sa.Text(), nullable=False),
    sa.Column('reponse_courte', sa.String(length=160), nullable=True),
    sa.Column('audio_url', sa.String(length=500), nullable=True),
    sa.Column('statut', sa.String(length=16), server_default='brouillon', nullable=False),
    sa.Column('date_maj', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("statut IN ('brouillon', 'en_revue', 'publie', 'archive')", name=op.f('ck_contenus_traductions_statut')),
    sa.CheckConstraint('char_length(reponse_courte) <= 160', name=op.f('ck_contenus_traductions_reponse_courte_160')),
    sa.ForeignKeyConstraint(['contenu_id'], ['contenus.id'], name=op.f('fk_contenus_traductions_contenu_id'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['langue_code'], ['langues.code'], name=op.f('fk_contenus_traductions_langue_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contenus_traductions')),
    sa.UniqueConstraint('contenu_id', 'langue_code', name='uq_contenus_traductions_contenu_langue'),
    )
    op.create_index(op.f('ix_contenus_traductions_contenu_id'), 'contenus_traductions', ['contenu_id'], unique=False)
    op.create_table('formulations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('contenu_id', sa.Integer(), nullable=False),
    sa.Column('langue_code', sa.String(length=8), nullable=False),
    sa.Column('texte', sa.String(length=300), nullable=False),
    sa.ForeignKeyConstraint(['contenu_id'], ['contenus.id'], name=op.f('fk_formulations_contenu_id'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['langue_code'], ['langues.code'], name=op.f('fk_formulations_langue_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_formulations')),
    )
    op.create_index(op.f('ix_formulations_contenu_id'), 'formulations', ['contenu_id'], unique=False)
    op.create_table('interactions',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('horodatage', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('canal', sa.String(length=20), nullable=False),
    sa.Column('langue_demandee', sa.String(length=8), nullable=False),
    sa.Column('langue_servie', sa.String(length=8), nullable=True),
    sa.Column('territoire_code', sa.String(length=16), nullable=True),
    sa.Column('usager_empreinte', sa.String(length=64), nullable=True),
    sa.Column('resultat', sa.String(length=10), nullable=False),
    sa.Column('motif_escalade', sa.String(length=40), nullable=True),
    sa.Column('contenu_id', sa.Integer(), nullable=True),
    sa.Column('score', sa.Double(), nullable=False),
    sa.Column('texte_masque', sa.String(length=500), nullable=False),
    sa.CheckConstraint("resultat IN ('reponse', 'escalade')", name=op.f('ck_interactions_resultat')),
    sa.ForeignKeyConstraint(['territoire_code'], ['coeur.territoires.code'], name=op.f('fk_interactions_territoire_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_interactions')),
    schema='coeur'
    )
    op.create_index(op.f('ix_interactions_horodatage'), 'interactions', ['horodatage'], unique=False, schema='coeur')
    op.create_index(op.f('ix_interactions_territoire_code'), 'interactions', ['territoire_code'], unique=False, schema='coeur')
    op.create_table('signalements',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('horodatage', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('canal', sa.String(length=20), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('territoire_code', sa.String(length=16), nullable=False),
    sa.Column('localite', sa.String(length=120), nullable=True),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('usager_empreinte', sa.String(length=64), nullable=True),
    sa.Column('statut', sa.String(length=16), server_default='nouveau', nullable=False),
    sa.CheckConstraint("statut IN ('nouveau', 'en_traitement', 'clos')", name=op.f('ck_signalements_statut')),
    sa.CheckConstraint("type IN ('menage_non_visite', 'rumeur', 'agent_douteux', 'autre')", name=op.f('ck_signalements_type')),
    sa.ForeignKeyConstraint(['territoire_code'], ['coeur.territoires.code'], name=op.f('fk_signalements_territoire_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signalements')),
    schema='coeur'
    )
    op.create_index(op.f('ix_signalements_horodatage'), 'signalements', ['horodatage'], unique=False, schema='coeur')
    op.create_index(op.f('ix_signalements_territoire_code'), 'signalements', ['territoire_code'], unique=False, schema='coeur')

    langues = sa.table(
        "langues", sa.column("code"), sa.column("nom"), sa.column("active")
    )
    op.bulk_insert(langues, LANGUES_INITIALES)
    _droits()


def downgrade() -> None:
    op.drop_index(op.f('ix_signalements_territoire_code'), table_name='signalements', schema='coeur')
    op.drop_index(op.f('ix_signalements_horodatage'), table_name='signalements', schema='coeur')
    op.drop_table('signalements', schema='coeur')
    op.drop_index(op.f('ix_interactions_territoire_code'), table_name='interactions', schema='coeur')
    op.drop_index(op.f('ix_interactions_horodatage'), table_name='interactions', schema='coeur')
    op.drop_table('interactions', schema='coeur')
    op.drop_index(op.f('ix_formulations_contenu_id'), table_name='formulations')
    op.drop_table('formulations')
    op.drop_index(op.f('ix_contenus_traductions_contenu_id'), table_name='contenus_traductions')
    op.drop_table('contenus_traductions')
    op.drop_index(op.f('ix_territoires_province_code'), table_name='territoires', schema='coeur')
    op.drop_table('territoires', schema='coeur')
    op.drop_table('langues')
    op.drop_table('contenus')
    op.drop_table('provinces', schema='coeur')
