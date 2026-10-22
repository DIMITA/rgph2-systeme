"""Réglages du cœur en base, chiffrés avec CLE_MAITRE

Révision : 0012
Précédente : 0011
Date : 2026-10-20 20:00:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('reglages',
    sa.Column('cle', sa.String(length=64), nullable=False),
    sa.Column('valeur', sa.Text(), nullable=False),
    sa.Column('modifie_a', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('cle', name=op.f('pk_reglages')),
    schema='coeur'
    )
    # L'API lit ses réglages ; seul le rôle propriétaire (assistant d'initialisation) les écrit.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rgph_api') THEN "
               "GRANT SELECT ON coeur.reglages TO rgph_api; END IF; END $$")


def downgrade() -> None:
    op.drop_table('reglages', schema='coeur')
