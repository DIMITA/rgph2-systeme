"""Service de transcription (transcription/serveur.py) avec un moteur factice.

Le décodage passe par le vrai ffmpeg, sur un vrai message au format de WhatsApp
(Ogg/Opus). Le modèle MMS lui-même n'est pas chargé : il est trop lourd pour les tests.
"""

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
if shutil.which("ffmpeg") is None:
    pytest.skip("ffmpeg absent", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

CHEMIN = Path(__file__).resolve().parents[2] / "transcription" / "serveur.py"
_spec = importlib.util.spec_from_file_location("serveur_transcription", CHEMIN)
serveur = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serveur)


class MoteurFactice:
    nom = "factice"

    def __init__(self):
        self.recus = []

    def langues(self):
        return ["fr", "ln"]

    def transcrire(self, signal, langue):
        self.recus.append((signal, langue))
        return f"{len(signal)} échantillons en {langue}"


def message_vocal(secondes: float) -> bytes:
    """Son de test au format des messages vocaux de WhatsApp (Ogg/Opus, 48 kHz)."""
    return subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
         "-i", f"sine=frequency=440:duration={secondes}", "-c:a", "libopus", "-f", "ogg", "pipe:1"],
        capture_output=True, check=True).stdout


@pytest.fixture
def service():
    moteur = MoteurFactice()
    return moteur, TestClient(serveur.creer_app(moteur, duree_max=10))


def test_sante(service):
    _, client = service
    assert client.get("/sante").json() == {"statut": "ok", "modele": "factice", "langues": ["fr", "ln"]}


def test_message_vocal_decode_en_16_khz(service):
    moteur, client = service
    r = client.post("/transcrire", params={"langue": "ln"}, content=message_vocal(2),
                    headers={"Content-Type": "audio/ogg"})
    assert r.status_code == 200
    assert r.json()["langue"] == "ln"
    [(signal, langue)] = moteur.recus
    assert signal.dtype == np.float32 and abs(len(signal) - 32_000) < 1_000
    # Sinusoïde de test de ffmpeg : amplitude 1/8.
    assert float(np.abs(signal).max()) == pytest.approx(0.125, abs=0.02)


def test_refus(service):
    _, client = service
    assert client.post("/transcrire", params={"langue": "lua"}, content=message_vocal(1)).status_code == 422
    assert client.post("/transcrire", params={"langue": "ln"}, content=b"pas du son").status_code == 422
    assert client.post("/transcrire", params={"langue": "ln"}, content=message_vocal(12)).status_code == 413


def test_codes_des_langues():
    assert serveur.codes_langues("fr:fra, ln:lin,kg:ktu") == {"fr": "fra", "ln": "lin", "kg": "ktu"}
