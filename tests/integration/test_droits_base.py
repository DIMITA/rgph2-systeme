"""Cloisonnement des rôles PostgreSQL : chacun ne peut faire que son travail."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from tests.conftest import URL_API, URL_DIRECTUS


@pytest.fixture(scope="module")
def api():
    moteur = create_engine(URL_API)
    yield moteur
    moteur.dispose()


@pytest.fixture(scope="module")
def directus():
    moteur = create_engine(URL_DIRECTUS)
    yield moteur
    moteur.dispose()


def refuse(moteur, sql):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with moteur.begin() as connexion:
            connexion.execute(text(sql))


def test_api_lit_les_contenus(api, exemples):
    with api.connect() as connexion:
        assert connexion.execute(text("SELECT count(*) FROM contenus")).scalar() == len(exemples)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO contenus (cle, statut) VALUES ('pirate', 'publie')",
        "UPDATE contenus_traductions SET statut = 'publie'",
        "DELETE FROM formulations",
        "INSERT INTO coeur.territoires VALUES ('X', 'X', 'ville', 'KIN')",
    ],
)
def test_api_ne_peut_pas_modifier_contenus_ni_referentiel(api, sql):
    refuse(api, sql)


def test_directus_ne_voit_pas_les_donnees_des_citoyens(directus):
    refuse(directus, "SELECT * FROM coeur.interactions")
    refuse(directus, "SELECT * FROM coeur.signalements")


def test_directus_edite_les_contenus(directus):
    with directus.begin() as connexion:
        connexion.execute(text("INSERT INTO contenus (cle) VALUES ('nouveau-brouillon')"))
