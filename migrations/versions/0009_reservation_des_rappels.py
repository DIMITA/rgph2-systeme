"""Rappels : heure de prise en charge, pour faire tomber les réservations oubliées

Révision : 0009
Précédente : 0008
Date : 2026-10-20 19:00:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Les rappels déjà « en cours » n'ont pas d'heure : leur réservation est tombée.
    op.add_column('rappels', sa.Column('pris_a', sa.DateTime(timezone=True), nullable=True),
                  schema='coeur')


def downgrade() -> None:
    op.drop_column('rappels', 'pris_a', schema='coeur')
