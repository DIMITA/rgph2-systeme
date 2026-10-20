"""Tests de bout en bout contre une vraie base PostgreSQL.

Prérequis : docker compose -f docker-compose.test.yml up -d
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tests.conftest import CLE_MINISTERE, CLE_USSD, CLE_WEB, URL_ADMIN

RACINE = Path(__file__).resolve().parents[2]
WEB = {"X-Cle-API": CLE_WEB}
USSD = {"X-Cle-API": CLE_USSD}
MINISTERE = {"X-Cle-API": CLE_MINISTERE}


@pytest.fixture(scope="session")
def moteur_admin():
    moteur = create_engine(URL_ADMIN)
    try:
        moteur.connect().close()
    except OperationalError:
        pytest.exit(
            "Base de test injoignable. Lancer : docker compose -f docker-compose.test.yml up -d",
            returncode=1,
        )
    config = Config(str(RACINE / "alembic.ini"))
    config.set_main_option("script_location", str(RACINE / "migrations"))
    config.attributes["url"] = URL_ADMIN
    # Repartir de zéro et vérifier au passage que les migrations s'annulent proprement.
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield moteur
    moteur.dispose()


@pytest.fixture(autouse=True)
def base_propre(moteur_admin):
    from coeur.connaissances.depot import cache
    from coeur.territoires.service import importer_csv

    with moteur_admin.begin() as connexion:
        connexion.execute(
            text(
                "TRUNCATE coeur.interactions, coeur.signalements, contenus, "
                "coeur.appels, coeur.rappels, coeur.enregistrements, coeur.ecoutes, "
                "coeur.badges, coeur.consultations, coeur.sms, coeur.preferences_langue, "
                "calendrier_passages, coeur.conversations_whatsapp, coeur.whatsapp_messages, "
                "coeur.abonnements_whatsapp, coeur.compteurs_debit, coeur.memoire_courte, "
                "coeur.remontees_terrain, coeur.appareils, "
                "coeur.territoires, coeur.provinces RESTART IDENTITY CASCADE"
            )
        )
    from coeur.mobile.service import limiteur_badges
    from coeur.sms.passerelle import passerelle
    from coeur.ussd.service import memoire
    from coeur.whatsapp import passerelle as wa_passerelle
    from coeur.whatsapp.service import deja_vus

    limiteur_badges().reinitialiser()
    passerelle().messages.clear()
    memoire.vider()
    deja_vus.vider()
    wa_passerelle.passerelle().messages.clear()
    with Session(moteur_admin) as session:
        importer_csv(session, RACINE / "donnees" / "territoires.csv")
    cache.invalider()


@pytest.fixture
def session_admin(moteur_admin):
    with Session(moteur_admin) as session:
        yield session


@pytest.fixture
def exemples(session_admin) -> dict[str, int]:
    from coeur.connaissances.exemples import EXEMPLES, charger_exemples

    ids = charger_exemples(session_admin)
    return {ex["cle"]: i for ex, i in zip(EXEMPLES, ids, strict=True)}


@pytest.fixture
def badges(session_admin, tmp_path) -> None:
    """AB1234 en service à Goma, XY9999 retiré (Kinshasa) ; tout autre badge est inconnu."""
    from coeur.badges.service import importer_csv
    from tests.conftest import PEPPER

    fichier = tmp_path / "badges.csv"
    fichier.write_text("numero,territoire_code,actif\nAB1234,NKV-GOM,1\nXY9999,KIN-V,0\n",
                       encoding="utf-8")
    importer_csv(session_admin, fichier, PEPPER)


@pytest.fixture
def client():
    from coeur.main import app

    with TestClient(app) as c:
        yield c
