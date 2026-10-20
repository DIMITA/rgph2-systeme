"""Réception des notifications de Meta (webhook) et envoi des réponses."""

import hashlib
import hmac
import threading
import time

from sqlalchemy.orm import Session

from coeur.commun import Canal
from coeur.config import Parametres
from coeur.confidentialite.service import normaliser_telephone
from coeur.connaissances.depot import Corpus
from coeur.mobile import service as mobile
from coeur.whatsapp.conversation import Contexte, Entree, traiter
from coeur.whatsapp.messages import Message
from coeur.whatsapp.modeles import MessageWhatsapp
from coeur.whatsapp.passerelle import passerelle

# Meta renvoie une notification restée sans réponse : un même message n'est traité qu'une fois.
DUREE_MEMOIRE = 3600


class DejaVus:
    def __init__(self) -> None:
        self._ids: dict[str, float] = {}
        self._verrou = threading.Lock()

    def nouveau(self, identifiant: str) -> bool:
        with self._verrou:
            maintenant = time.monotonic()
            for i in [i for i, t in self._ids.items() if maintenant - t > DUREE_MEMOIRE]:
                del self._ids[i]
            if identifiant in self._ids:
                return False
            self._ids[identifiant] = maintenant
            return True

    def vider(self) -> None:
        with self._verrou:
            self._ids.clear()


deja_vus = DejaVus()


def signature_valide(corps: bytes, signature: str | None, secret: str) -> bool:
    """En-tête X-Hub-Signature-256 : « sha256= » + HMAC-SHA256 du corps avec le secret de l'app."""
    if not secret or not signature or not signature.startswith("sha256="):
        return False
    attendu = hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), attendu)


def lire_entree(message: dict) -> Entree:
    type_ = message.get("type")
    if type_ == "text":
        return Entree("texte", message.get("text", {}).get("body", ""))
    if type_ == "interactive":
        interactif = message.get("interactive", {})
        reponse = interactif.get("list_reply") or interactif.get("button_reply") or {}
        return Entree("choix", reponse.get("id", "menu"))
    if type_ == "button":  # bouton d'un modèle de message (rappels de passage)
        return Entree("choix", message.get("button", {}).get("payload", "menu"))
    return Entree("autre")


def envoyer(session: Session, numero: str, empreinte: str, messages: list[Message],
            categorie: str = "service") -> bool:
    tous = True
    for message in messages:
        ok = passerelle().envoyer(numero, message)
        tous = tous and ok
        session.add(MessageWhatsapp(sens="sortant", usager_empreinte=empreinte,
                                    categorie=categorie, statut="envoye" if ok else "echec"))
    session.commit()
    return tous


def recevoir_message(session: Session, corpus: Corpus, reglages: Parametres,
                     message: dict) -> list[Message] | None:
    """Traite un message reçu et envoie la réponse. None : message ignoré."""
    if not deja_vus.nouveau(message.get("id", "")):
        return None
    try:
        numero = normaliser_telephone(message.get("from", ""))
    except ValueError:
        return None
    u = mobile.usager(session, Canal.WHATSAPP, numero, reglages)
    session.add(MessageWhatsapp(sens="entrant", usager_empreinte=u.empreinte, statut="recu"))
    session.commit()
    entree = lire_entree(message)
    premier_contact = (mobile.langue_preferee(session, u.empreinte) is None
                       and not entree.valeur.startswith("langue:"))
    reponses = traiter(Contexte(session, corpus, reglages, u), entree, premier_contact)
    envoyer(session, numero, u.empreinte, reponses)
    return reponses


def recevoir(session: Session, corpus: Corpus, reglages: Parametres, notification: dict) -> int:
    """Notification du webhook : peut contenir plusieurs messages, ou des accusés (ignorés)."""
    traites = 0
    for entree in notification.get("entry", []):
        for changement in entree.get("changes", []):
            for message in changement.get("value", {}).get("messages", []):
                if recevoir_message(session, corpus, reglages, message) is not None:
                    traites += 1
    return traites
