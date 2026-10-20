"""Texte des questions facultatif (CONSERVATION_TEXTE_QUESTIONS)

Révision : 0008
Précédente : 0007
Date : 2026-10-20 18:30:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('interactions', 'texte_masque', existing_type=sa.String(length=500),
                    nullable=True, schema='coeur')


def downgrade() -> None:
    op.execute("UPDATE coeur.interactions SET texte_masque = '' WHERE texte_masque IS NULL")
    op.alter_column('interactions', 'texte_masque', existing_type=sa.String(length=500),
                    nullable=False, schema='coeur')
