"""Envoi des SMS : par Kannel en exploitation, en mémoire pour les tests.

Kannel (passerelle SMS open source, dossier sms/ du dépôt) est hébergé avec le cœur
et se branche directement chez l'opérateur (SMPP) : aucun service étranger ne voit
passer les messages des citoyens.
"""

import logging
import threading
from collections import deque
from functools import lru_cache
from typing import Protocol

import httpx

from coeur.config import parametres

journal = logging.getLogger(__name__)


class Passerelle(Protocol):
    def envoyer(self, numero: str, texte: str) -> bool:
        """`numero` au format international sans « + » (ex. 243812345678)."""


class PasserelleSimulation:
    """Garde les derniers messages en mémoire (tests et démonstrations)."""

    def __init__(self, taille: int = 200):
        self.messages: deque[tuple[str, str]] = deque(maxlen=taille)
        self._verrou = threading.Lock()

    def envoyer(self, numero: str, texte: str) -> bool:
        with self._verrou:
            self.messages.append((numero, texte))
        return True

    def derniers(self, numero: str) -> list[str]:
        with self._verrou:
            return [t for n, t in self.messages if n == numero]


class PasserelleKannel:
    """Interface « sendsms » de Kannel (smsbox)."""

    def __init__(self, url: str, utilisateur: str, mdp: str, expediteur: str):
        self.url, self.utilisateur, self.mdp, self.expediteur = url, utilisateur, mdp, expediteur
        self.http = httpx.Client(timeout=10)

    def envoyer(self, numero: str, texte: str) -> bool:
        try:
            r = self.http.get(self.url, params={
                "username": self.utilisateur, "password": self.mdp, "to": f"+{numero}",
                "from": self.expediteur, "text": texte, "charset": "UTF-8",
            })
        except httpx.HTTPError as erreur:
            journal.warning("Kannel injoignable : %s", type(erreur).__name__)
            return False
        if r.status_code >= 300:
            # Jamais le numéro ni le texte dans le journal.
            journal.warning("Kannel a refusé un SMS : %s %s", r.status_code, r.text[:80])
            return False
        return True


@lru_cache
def passerelle() -> Passerelle:
    reglages = parametres()
    if reglages.sms_passerelle == "kannel":
        return PasserelleKannel(reglages.kannel_url, reglages.kannel_utilisateur,
                                reglages.kannel_mdp, reglages.sms_expediteur)
    if reglages.sms_passerelle != "simulation":
        raise ValueError(f"SMS_PASSERELLE inconnue : {reglages.sms_passerelle!r}")
    return PasserelleSimulation()
