"""Envoi d'une suite de messages, journalisé (sans texte ni numéro)."""

from sqlalchemy.orm import Session

from coeur.whatsapp.messages import Message
from coeur.whatsapp.modeles import MessageWhatsapp
from coeur.whatsapp.passerelle import passerelle


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
