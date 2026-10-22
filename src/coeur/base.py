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
    reglages = parametres()
    return create_engine(
        reglages.database_url, pool_pre_ping=True, pool_size=reglages.base_connexions,
        max_overflow=max(reglages.base_connexions_max - reglages.base_connexions, 0))


@lru_cache
def moteur_court() -> Engine:
    """Pool à part pour les compteurs et la mémoire courte (`coeur.limiteur`).

    Une requête qui tient déjà sa connexion en demande une seconde pour un compteur.
    Dans le même pool, sous charge, toutes les requêtes tiendraient une connexion et
    attendraient chacune la seconde : interblocage jusqu'au délai d'attente (constaté
    au test de charge). Ces opérations sont brèves et ne s'imbriquent jamais : un petit
    pool séparé ne peut pas se bloquer.
    """
    return create_engine(parametres().database_url, pool_pre_ping=True, pool_size=3,
                         max_overflow=7)


@lru_cache
def _fabrique() -> sessionmaker[Session]:
    return sessionmaker(bind=moteur_sql(), expire_on_commit=False)


def nouvelle_session() -> Session:
    return _fabrique()()


def session_db() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête."""
    with nouvelle_session() as session:
        yield session
