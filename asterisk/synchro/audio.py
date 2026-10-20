"""Préparation des fichiers audio au format téléphonique (WAV 8 kHz, mono, 16 bits)."""

import subprocess
import tempfile
from pathlib import Path

SONS = Path("/var/lib/asterisk/sounds")
FORMATS_SOURCE = (".wav", ".mp3", ".ogg", ".m4a", ".opus")


def dossier_rgph(langue: str) -> Path:
    """Asterisk cherche les sons dans sounds/<langue>/ selon la langue de l'appel."""
    return SONS / langue / "rgph"


def convertir(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(source),
         "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", str(destination)],
        check=True,
    )


def synthetiser(texte: str, destination: Path) -> None:
    """Voix de synthèse française PROVISOIRE, en attendant les enregistrements."""
    with tempfile.TemporaryDirectory() as tmp:
        brut = Path(tmp) / "synthese.wav"
        subprocess.run(["espeak-ng", "-v", "fr", "-s", "145", "-w", str(brut), texte],
                       check=True)
        convertir(brut, destination)


def source_enregistree(dossier: Path, nom: str) -> Path | None:
    """Fichier enregistré par un locuteur (nom.wav, nom.mp3…), s'il existe."""
    for extension in FORMATS_SOURCE:
        chemin = dossier / f"{nom}{extension}"
        if chemin.is_file():
            return chemin
    return None
