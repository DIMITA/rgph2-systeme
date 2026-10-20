"""Envoi des messages WhatsApp : API Graph de Meta en exploitation, en mémoire pour les tests."""

import logging
import threading
from collections import deque
from functools import lru_cache
from typing import Protocol

import httpx

from coeur.config import parametres
from coeur.whatsapp.messages import Message, charge_utile

journal = logging.getLogger(__name__)


class Passerelle(Protocol):
    def envoyer(self, numero: str, message: Message) -> bool:
        """`numero` : identifiant WhatsApp de l'usager (numéro international sans « + »)."""


class PasserelleSimulation:
    """Garde les derniers messages en mémoire (tests, simulateur de téléphone)."""

    def __init__(self, taille: int = 500):
        self.messages: deque[tuple[str, Message]] = deque(maxlen=taille)
        self._verrou = threading.Lock()

    def envoyer(self, numero: str, message: Message) -> bool:
        with self._verrou:
            self.messages.append((numero, message))
        return True

    def derniers(self, numero: str) -> list[Message]:
        with self._verrou:
            return [m for n, m in self.messages if n == numero]


class PasserelleMeta:
    """API officielle (« Cloud API ») : POST {graph}/{numero_id}/messages."""

    def __init__(self, url: str, numero_id: str, jeton: str):
        self.url = f"{url.rstrip('/')}/{numero_id}/messages"
        self.http = httpx.Client(timeout=15, headers={"Authorization": f"Bearer {jeton}"})

    def envoyer(self, numero: str, message: Message) -> bool:
        try:
            r = self.http.post(self.url, json=charge_utile(numero, message))
        except httpx.HTTPError as erreur:
            journal.warning("API WhatsApp injoignable : %s", type(erreur).__name__)
            return False
        if r.status_code >= 300:
            # Le code d'erreur de Meta seulement : jamais le numéro ni le texte.
            try:
                code = r.json().get("error", {}).get("code")
            except ValueError:
                code = None
            journal.warning("API WhatsApp : refus %s (code %s)", r.status_code, code)
            return False
        return True


@lru_cache
def passerelle() -> Passerelle:
    reglages = parametres()
    if reglages.whatsapp_passerelle == "meta":
        return PasserelleMeta(reglages.whatsapp_graph_url, reglages.whatsapp_numero_id,
                              reglages.whatsapp_jeton)
    if reglages.whatsapp_passerelle != "simulation":
        raise ValueError(f"WHATSAPP_PASSERELLE inconnue : {reglages.whatsapp_passerelle!r}")
    return PasserelleSimulation()
