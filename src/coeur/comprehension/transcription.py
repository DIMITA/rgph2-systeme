"""Transcription des messages vocaux. La voix n'est jamais enregistrée : elle ne
fait que traverser la mémoire, le temps d'obtenir le texte.

Contrat du service (`TRANSCRIPTION=service`) :
    POST {TRANSCRIPTION_URL}/transcrire?langue=ln
    Content-Type: type du fichier (audio/ogg, audio/mpeg, audio/wav…)
    corps : le fichier audio
    → 200 {"texte": "…"}
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from coeur.config import Parametres, parametres

journal = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transcription:
    texte: str


class Transcripteur(Protocol):
    def transcrire(self, audio: bytes, type_mime: str, langue: str) -> Transcription | None:
        """None si la transcription a échoué (service injoignable, son illisible)."""


class TranscripteurService:
    def __init__(self, url: str, delai: float):
        self.url = f"{url.rstrip('/')}/transcrire"
        self.delai = delai

    def transcrire(self, audio: bytes, type_mime: str, langue: str) -> Transcription | None:
        try:
            r = httpx.post(self.url, params={"langue": langue}, content=audio,
                           headers={"Content-Type": type_mime or "application/octet-stream"},
                           timeout=self.delai)
        except httpx.HTTPError as erreur:
            journal.warning("Service de transcription injoignable : %s", type(erreur).__name__)
            return None
        if r.status_code != 200:
            # Le code seulement : jamais le contenu, qui pourrait reprendre la transcription.
            journal.warning("Service de transcription : refus %s", r.status_code)
            return None
        try:
            texte = r.json()["texte"]
        except (ValueError, KeyError, TypeError):
            journal.warning("Service de transcription : réponse illisible")
            return None
        return Transcription(texte.strip()) if isinstance(texte, str) and texte.strip() else None


class TranscripteurSimulation:
    """Le « son » est un texte UTF-8 : il est rendu tel quel (b"" = son incompris)."""

    def transcrire(self, audio: bytes, type_mime: str, langue: str) -> Transcription | None:
        texte = audio.decode("utf-8", errors="ignore").strip()
        return Transcription(texte) if texte else None


@lru_cache
def transcripteur() -> Transcripteur | None:
    reglages = parametres()
    if reglages.transcription == "service":
        return TranscripteurService(reglages.transcription_url, reglages.transcription_delai_secondes)
    if reglages.transcription == "simulation":
        return TranscripteurSimulation()
    return None


def langue_ouverte(langue: str, reglages: Parametres) -> bool:
    """Vrai si les messages vocaux dans cette langue sont transcrits."""
    return reglages.transcription != "aucune" and langue in reglages.langues_transcription()
