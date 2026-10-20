"""Accès à la base de données."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from coeur.config import parametres

# Schéma propre à l'API : invisible pour Directus.
SCHEMA_COEUR = "coeur"
# Les contenus éditoriaux (administrés dans Directus) sont dans le schéma par défaut, public.

CONVENTION_NOMMAGE = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENTION_NOMMAGE)


@lru_cache
def moteur_sql() -> Engine:
    return create_engine(parametres().database_url, pool_pre_ping=True)


@lru_cache
def _fabrique() -> sessionmaker[Session]:
    return sessionmaker(bind=moteur_sql(), expire_on_commit=False)


def nouvelle_session() -> Session:
    return _fabrique()()


def session_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête."""
    with nouvelle_session() as session:
        yield session
