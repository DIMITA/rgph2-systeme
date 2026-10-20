"""Interactions : question écrite ou dite (message vocal transcrit)

Révision : 0011
Précédente : 0010
Date : 2026-10-20 19:30:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('interactions', sa.Column('entree', sa.String(length=8),
                                            server_default='texte', nullable=False),
                  schema='coeur')
    op.create_check_constraint(op.f('ck_interactions_entree'), 'interactions',
                               "entree IN ('texte', 'voix')", schema='coeur')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_interactions_entree'), 'interactions', schema='coeur')
    op.drop_column('interactions', 'entree', schema='coeur')
