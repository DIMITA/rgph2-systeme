"""Messages envoyés par le bot, et leur traduction au format de l'API de Meta.

Limites de WhatsApp (refusées par Meta si dépassées) : 10 lignes par liste, titre de
ligne de 24 caractères, description de 72, bouton de 20, 3 boutons de réponse,
corps d'un message interactif de 1 024 caractères, texte simple de 4 096.
"""

from dataclasses import dataclass, field

from coeur.mobile.gsm import couper

MAX_LIGNES = 10
MAX_TITRE_LIGNE = 24
MAX_DESCRIPTION = 72
MAX_BOUTON = 20
MAX_BOUTONS = 3
MAX_CORPS_INTERACTIF = 1024
MAX_TEXTE = 4096


@dataclass
class Texte:
    corps: str


@dataclass
class Ligne:
    id: str
    titre: str
    description: str | None = None


@dataclass
class Liste:
    """Menu déroulant : un bouton qui ouvre jusqu'à 10 choix."""

    corps: str
    bouton: str
    lignes: list[Ligne] = field(default_factory=list)


@dataclass
class Boutons:
    """Jusqu'à 3 boutons de réponse sous un texte."""

    corps: str
    boutons: list[tuple[str, str]]


@dataclass
class Media:
    """Audio ou vidéo, par lien public HTTPS (Meta télécharge le fichier)."""

    type: str  # « audio » ou « video »
    lien: str
    legende: str | None = None


@dataclass
class Modele:
    """Message pré-approuvé par Meta, seul permis hors de la fenêtre de 24 h (facturé).

    `parametres` remplissent {{1}}, {{2}}… du corps ; `bouton_stop` ajoute la charge
    utile « stop » au bouton de réponse rapide du modèle (arrêt des rappels).
    """

    nom: str
    langue: str
    parametres: list[str]
    bouton_stop: bool = True


Message = Texte | Liste | Boutons | Media | Modele


def charge_utile(numero: str, message: Message) -> dict:
    """Corps de la requête « POST /{numero_id}/messages » de l'API Graph."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": numero}
    if isinstance(message, Texte):
        return {**base, "type": "text",
                "text": {"body": message.corps[:MAX_TEXTE], "preview_url": False}}
    if isinstance(message, Modele):
        composants = [{"type": "body", "parameters": [{"type": "text", "text": p}
                                                       for p in message.parametres]}]
        if message.bouton_stop:
            composants.append({"type": "button", "sub_type": "quick_reply", "index": "0",
                               "parameters": [{"type": "payload", "payload": "stop"}]})
        return {**base, "type": "template", "template": {
            "name": message.nom, "language": {"code": message.langue}, "components": composants}}
    if isinstance(message, Media):
        media = {"link": message.lien}
        if message.legende and message.type == "video":
            media["caption"] = message.legende[:MAX_CORPS_INTERACTIF]
        return {**base, "type": message.type, message.type: media}
    if isinstance(message, Liste):
        lignes = [{"id": l.id, "title": couper(l.titre, MAX_TITRE_LIGNE),
                   **({"description": couper(l.description, MAX_DESCRIPTION)}
                      if l.description else {})}
                  for l in message.lignes[:MAX_LIGNES]]
        return {**base, "type": "interactive", "interactive": {
            "type": "list",
            "body": {"text": message.corps[:MAX_CORPS_INTERACTIF]},
            "action": {"button": couper(message.bouton, MAX_BOUTON),
                       "sections": [{"title": couper(message.bouton, MAX_TITRE_LIGNE),
                                     "rows": lignes}]},
        }}
    return {**base, "type": "interactive", "interactive": {
        "type": "button",
        "body": {"text": message.corps[:MAX_CORPS_INTERACTIF]},
        "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": couper(t, MAX_BOUTON)}}
                               for i, t in message.boutons[:MAX_BOUTONS]]},
    }}
