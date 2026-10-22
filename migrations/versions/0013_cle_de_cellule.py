"""Perturbation des statistiques : clé aléatoire secrète par interaction et par signalement

Révision : 0013
Précédente : 0012
Date : 2026-10-20 21:00:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None

TABLES = ('interactions', 'signalements')


def upgrade() -> None:
    # Valeur par défaut volatile : PostgreSQL tire une clé différente pour chaque ligne
    # existante, puis pour chaque nouvelle ligne.
    for table in TABLES:
        op.add_column(table, sa.Column('cle_cellule', sa.SmallInteger(), nullable=False,
                                       server_default=sa.text('floor(random() * 256)::smallint')),
                      schema='coeur')


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, 'cle_cellule', schema='coeur')
