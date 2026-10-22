import httpx
import pytest

from coeur.comprehension import transcription as t
from coeur.config import parametres


def reponse(statut=200, json=None, contenu=None):
    return httpx.Response(statut, json=json, content=contenu,
                          request=httpx.Request("POST", "http://transcription:9000/transcrire"))


class Appels(list):
    """Requêtes reçues par le faux service, et la réponse qu'il renvoie."""

    reponse: httpx.Response


@pytest.fixture
def appels(monkeypatch):
    journal = Appels()

    def faux_post(url, **kwargs):
        journal.append((url, kwargs))
        return journal.reponse

    monkeypatch.setattr(t.httpx, "post", faux_post)
    return journal


def service():
    return t.TranscripteurService("http://transcription:9000/", delai=5)


def test_contrat_du_service(appels):
    appels.reponse = reponse(json={"texte": "  Ntango nini bakoya ?  "})
    assert service().transcrire(b"OggS...", "audio/ogg", "ln") == t.Transcription("Ntango nini bakoya ?")
    [(url, kwargs)] = appels
    assert url == "http://transcription:9000/transcrire"
    assert kwargs["params"] == {"langue": "ln"}
    assert kwargs["content"] == b"OggS..."
    assert kwargs["headers"]["Content-Type"] == "audio/ogg"


@pytest.mark.parametrize("r", [
    reponse(500), reponse(json={"autre": 1}), reponse(contenu=b"pas du json"), reponse(json={"texte": " "}),
])
def test_echecs_du_service(appels, r):
    appels.reponse = r
    assert service().transcrire(b"x", "audio/ogg", "ln") is None


def test_service_injoignable(monkeypatch):
    def panne(url, **kwargs):
        raise httpx.ConnectError("refusé")

    monkeypatch.setattr(t.httpx, "post", panne)
    assert service().transcrire(b"x", "audio/ogg", "ln") is None


def test_simulation():
    assert t.TranscripteurSimulation().transcrire("Bonjour".encode(), "", "fr").texte == "Bonjour"
    assert t.TranscripteurSimulation().transcrire(b"", "", "fr") is None


def test_langues_ouvertes_une_a_une(monkeypatch):
    reglages = parametres()
    monkeypatch.setattr(reglages, "transcription", "service")
    monkeypatch.setattr(reglages, "transcription_langues", "sw, ln")
    assert t.langue_ouverte("ln", reglages) and t.langue_ouverte("sw", reglages)
    assert not t.langue_ouverte("lua", reglages)
    monkeypatch.setattr(reglages, "transcription", "aucune")
    assert not t.langue_ouverte("ln", reglages)
