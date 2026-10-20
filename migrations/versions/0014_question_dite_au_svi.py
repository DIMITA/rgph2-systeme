"""Question dite au serveur vocal : sujet compris en attente de confirmation

Révision : 0014
Précédente : 0013
Date : 2026-10-20 23:00:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('appels', sa.Column('question_texte', sa.Text()), schema='coeur')
    op.add_column('appels', sa.Column('question_contenu_id', sa.Integer()), schema='coeur')
    op.add_column('appels', sa.Column('question_score', sa.Float()), schema='coeur')


def downgrade() -> None:
    for colonne in ('question_score', 'question_contenu_id', 'question_texte'):
        op.drop_column('appels', colonne, schema='coeur')
