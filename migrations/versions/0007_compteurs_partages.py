"""Compteurs de débit et mémoire courte partagés entre processus (tables UNLOGGED)

Révision : 0007
Précédente : 0006
Date : 2026-10-20 18:00:00
"""

import sqlalchemy as sa
from alembic import op


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('compteurs_debit',
    sa.Column('cle', sa.String(length=64), nullable=False),
    sa.Column('fenetre', sa.BigInteger(), nullable=False),
    sa.Column('nb', sa.Integer(), nullable=False),
    sa.Column('expire_a', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('cle', 'fenetre', name=op.f('pk_compteurs_debit')),
    schema='coeur',
    prefixes=['UNLOGGED'],
    )
    op.create_index(op.f('ix_compteurs_debit_expire_a'), 'compteurs_debit', ['expire_a'], unique=False, schema='coeur')
    op.create_table('memoire_courte',
    sa.Column('cle', sa.String(length=64), nullable=False),
    sa.Column('valeur', sa.JSON(), nullable=True),
    sa.Column('expire_a', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('cle', name=op.f('pk_memoire_courte')),
    schema='coeur',
    prefixes=['UNLOGGED'],
    )
    op.create_index(op.f('ix_memoire_courte_expire_a'), 'memoire_courte', ['expire_a'], unique=False, schema='coeur')
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'rgph_api') THEN "
               "GRANT SELECT, INSERT, UPDATE, DELETE ON coeur.compteurs_debit, coeur.memoire_courte "
               "TO rgph_api; END IF; END $$")


def downgrade() -> None:
    op.drop_index(op.f('ix_memoire_courte_expire_a'), table_name='memoire_courte', schema='coeur')
    op.drop_table('memoire_courte', schema='coeur')
    op.drop_index(op.f('ix_compteurs_debit_expire_a'), table_name='compteurs_debit', schema='coeur')
    op.drop_table('compteurs_debit', schema='coeur')
