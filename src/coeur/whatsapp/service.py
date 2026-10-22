"""Réception des notifications de Meta (webhook) et envoi des réponses."""

import hashlib
import hmac
from collections.abc import Callable

from sqlalchemy.orm import Session

from coeur.base import nouvelle_session
from coeur.commun import Canal
from coeur.config import Parametres, parametres
from coeur.confidentialite.service import normaliser_telephone
from coeur.connaissances.depot import Corpus, cache
from coeur.limiteur import MemoireCourte
from coeur.mobile import service as mobile
from coeur.whatsapp.conversation import Contexte, Entree, traiter
from coeur.whatsapp.envoi import envoyer
from coeur.whatsapp.messages import Message
from coeur.whatsapp.modeles import MessageWhatsapp

# Meta renvoie une notification restée sans réponse : un même message n'est traité qu'une fois.
DUREE_MEMOIRE = 3600


deja_vus = MemoireCourte("whatsapp", DUREE_MEMOIRE)


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
    if type_ == "audio" and message.get("audio", {}).get("id"):
        return Entree("vocal", message["audio"]["id"])
    return Entree("autre")


# Planifie une fonction après la réponse au webhook (BackgroundTasks.add_task).
Differer = Callable[..., None]


def recevoir_message(session: Session, corpus: Corpus, reglages: Parametres,
                     message: dict, differer: Differer | None = None) -> list[Message] | None:
    """Traite un message reçu et envoie la réponse. None : message ignoré.

    Un message vocal est traité après la réponse à Meta si `differer` est fourni : la
    transcription prend plusieurs secondes, et Meta renvoie une notification restée
    trop longtemps sans réponse. Il renvoie alors une liste vide.
    """
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
    if entree.type == "vocal" and not premier_contact and differer is not None:
        differer(traiter_vocal, numero, entree)
        return []
    reponses = traiter(Contexte(session, corpus, reglages, u), entree, premier_contact)
    envoyer(session, numero, u.empreinte, reponses)
    return reponses


def traiter_vocal(numero: str, entree: Entree) -> None:
    """Message vocal différé : sa propre session, la requête du webhook étant terminée."""
    reglages = parametres()
    with nouvelle_session() as session:
        corpus = cache.obtenir(session, reglages.cache_contenus_secondes)
        u = mobile.usager(session, Canal.WHATSAPP, numero, reglages)
        reponses = traiter(Contexte(session, corpus, reglages, u), entree, False)
        envoyer(session, numero, u.empreinte, reponses)


def recevoir(session: Session, corpus: Corpus, reglages: Parametres, notification: dict,
             differer: Differer | None = None) -> int:
    """Notification du webhook : peut contenir plusieurs messages, ou des accusés (ignorés)."""
    traites = 0
    for entree in notification.get("entry", []):
        for changement in entree.get("changes", []):
            for message in changement.get("value", {}).get("messages", []):
                if recevoir_message(session, corpus, reglages, message, differer) is not None:
                    traites += 1
    return traites
