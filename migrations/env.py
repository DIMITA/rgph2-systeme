import os

from alembic import context
from sqlalchemy import create_engine, text

from coeur.base import SCHEMA_COEUR
from coeur.modeles import Base

cible = Base.metadata
# Les tests passent l'URL du rôle propriétaire par config.attributes.
url = context.config.attributes.get("url") or os.environ["DATABASE_URL"]


def inclure(objet, nom, type_, reflete, compare_a) -> bool:
    # Ne jamais toucher aux tables que nous ne décrivons pas (tables directus_*).
    if type_ == "table" and reflete and compare_a is None:
        return False
    return True


def executer() -> None:
    moteur = create_engine(url)
    with moteur.begin() as connexion:
        connexion.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_COEUR}"))
        context.configure(
            connection=connexion,
            target_metadata=cible,
            include_schemas=True,
            include_object=inclure,
            version_table_schema=SCHEMA_COEUR,
        )
        context.run_migrations()


executer()
