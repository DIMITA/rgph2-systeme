"""AGI de la question dite : protocole, effacement de l'enregistrement, garde-fous."""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "asterisk" / "synchro"))

import question_vocale  # noqa: E402

VARIABLES = {"LANGUE": "fr", "API": "http://api:8000", "CLE_API": "cle", "APPEL": "a1"}


class Asterisk:
    """Côté Asterisk du dialogue AGI : répond aux GET VARIABLE, note les SET VARIABLE."""

    def __init__(self):
        self.a_lire = ["agi_request: question_vocale.py\n", "agi_channel: PJSIP/x\n", "\n"]
        self.ecrites = {}

    def readline(self):
        return self.a_lire.pop(0) if self.a_lire else ""

    def write(self, texte):
        commande = texte.strip()
        reponse = "200 result=1"
        if commande.startswith("GET VARIABLE "):
            nom = commande.removeprefix("GET VARIABLE ")
            reponse = f"200 result=1 ({VARIABLES[nom]})" if nom in VARIABLES else "200 result=0"
        elif commande.startswith("SET VARIABLE "):
            nom, valeur = commande.removeprefix("SET VARIABLE ").split(" ", 1)
            self.ecrites[nom] = valeur.strip('"')
        self.a_lire.append(reponse + "\n")

    def flush(self):
        pass


@pytest.fixture
def dossiers(tmp_path, monkeypatch):
    questions = tmp_path / "questions"
    questions.mkdir()
    sons = tmp_path / "sons"
    (sons / "fr" / "rgph" / "svi").mkdir(parents=True)
    monkeypatch.setattr(question_vocale, "DOSSIER", questions)
    monkeypatch.setattr(question_vocale, "dossier_rgph", lambda langue: sons / langue / "rgph")
    return questions, sons / "fr" / "rgph" / "svi"


def lancer(monkeypatch, fichier: Path, reponse=None, erreur=None) -> dict:
    envoyes = []

    def demander(api, cle, appel, langue, audio):
        envoyes.append((api, cle, appel, langue, audio))
        if erreur:
            raise erreur
        return reponse

    monkeypatch.setattr(question_vocale, "demander", demander)
    canal = Asterisk()
    monkeypatch.setattr(question_vocale.sys, "argv", ["question_vocale.py", str(fichier)])
    question_vocale.main(question_vocale.Agi(canal, canal))
    return {"variables": canal.ecrites, "envoyes": envoyes}


def test_sujet_propose_et_enregistrement_efface(dossiers, monkeypatch):
    questions, svi = dossiers
    (svi / "q-7.wav").write_bytes(b"q")
    (svi / "r-7.wav").write_bytes(b"r")
    fichier = questions / "u1-0.wav"
    fichier.write_bytes(b"RIFF voix")
    resultat = lancer(monkeypatch, fichier, {"issue": "proposition", "contenu_id": 7})
    assert resultat["variables"] == {"QV_ISSUE": "proposition", "QV_CONTENU": "7"}
    assert resultat["envoyes"] == [("http://api:8000", "cle", "a1", "fr", b"RIFF voix")]
    assert not fichier.exists()


def test_sans_audio_du_sujet_conseiller(dossiers, monkeypatch):
    questions, _ = dossiers
    fichier = questions / "u2-0.wav"
    fichier.write_bytes(b"voix")
    resultat = lancer(monkeypatch, fichier, {"issue": "proposition", "contenu_id": 7})
    assert resultat["variables"]["QV_ISSUE"] == "conseiller"


def test_coeur_injoignable_conseiller_et_efface(dossiers, monkeypatch):
    questions, _ = dossiers
    fichier = questions / "u3-0.wav"
    fichier.write_bytes(b"voix")
    resultat = lancer(monkeypatch, fichier, erreur=OSError("refusé"))
    assert resultat["variables"]["QV_ISSUE"] == "conseiller"
    assert not fichier.exists()


def test_rien_enregistre(dossiers, monkeypatch):
    questions, _ = dossiers
    resultat = lancer(monkeypatch, questions / "absent.wav")
    assert resultat["variables"]["QV_ISSUE"] == "conseiller" and resultat["envoyes"] == []


def test_fichier_hors_du_dossier_jamais_lu_ni_efface(dossiers, monkeypatch, tmp_path):
    autre = tmp_path / "secret.wav"
    autre.write_bytes(b"x")
    resultat = lancer(monkeypatch, autre)
    assert resultat["envoyes"] == [] and autre.exists()


def test_vraie_requete_http(monkeypatch):
    """demander() : POST du son brut, clé en en-tête, appel et langue en paramètres."""
    vus = {}

    class Reponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def urlopen(requete, timeout):
        vus.update(url=requete.full_url, corps=requete.data, cle=requete.get_header("X-cle-api"),
                   type=requete.get_header("Content-type"), methode=requete.get_method())
        return Reponse(json.dumps({"issue": "conseiller"}).encode())

    monkeypatch.setattr(question_vocale.urllib.request, "urlopen", urlopen)
    assert question_vocale.demander("http://api", "k", "a.1", "ln", b"son") == {
        "issue": "conseiller"}
    assert vus == {"url": "http://api/v1/appels/question-vocale?appel=a.1&langue=ln",
                   "corps": b"son", "cle": "k", "type": "audio/wav", "methode": "POST"}
