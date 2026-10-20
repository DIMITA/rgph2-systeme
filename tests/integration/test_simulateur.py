"""Page « simulateur de téléphone » : absente par défaut, utilisable en test."""

import pytest

from coeur.config import parametres


def test_absent_par_defaut(client):
    assert client.get("/simulateur").status_code == 404
    assert client.post("/simulateur/sms", data={"numero": "0810000000", "message": "AIDE"}
                       ).status_code == 404


def test_jamais_en_production(client, monkeypatch):
    monkeypatch.setattr(parametres(), "simulateur_mobile", True)
    monkeypatch.setattr(parametres(), "environnement", "production")
    assert client.get("/simulateur").status_code == 404


@pytest.fixture
def simulateur(client, monkeypatch):
    monkeypatch.setattr(parametres(), "simulateur_mobile", True)
    return client


def test_session_ussd(simulateur):
    page = simulateur.post("/simulateur/ussd", data={"numero": "0810000000"}).text
    assert "Choisissez votre langue" in page
    session = page.split('name="session_ussd" value="')[1].split('"')[0]
    page = simulateur.post("/simulateur/ussd", data={
        "numero": "0810000000", "session_ussd": session, "historique": "", "saisie": "1"}).text
    assert "Questions fréquentes" in page
    assert 'name="historique" value="1"' in page


def test_sms(simulateur):
    page = simulateur.post("/simulateur/sms", data={"numero": "0810000000", "message": "AIDE"}).text
    assert "RGPH-2 : envoyez votre question" in page
    assert "Envoi de la réponse : envoye" in page
