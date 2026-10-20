"""Importe tous les modèles pour que les migrations les voient."""

from coeur.badges.modeles import Badge
from coeur.base import Base
from coeur.calendrier.modeles import Passage
from coeur.centre_appels.modeles import Appel, Ecoute, Enregistrement, Rappel
from coeur.connaissances.modeles import Contenu, Formulation, Langue, Traduction
from coeur.interactions.modeles import Interaction
from coeur.limiteur import CompteurDebit, Marque
from coeur.mobile.modeles import Consultation, MessageSms, PreferenceLangue
from coeur.signalements.modeles import Signalement
from coeur.terrain.modeles import Appareil, RemonteeRecue
from coeur.territoires.modeles import Province, Territoire
from coeur.whatsapp.modeles import Abonnement, Conversation, MessageWhatsapp

__all__ = [
    "Abonnement", "Appareil", "Appel", "Badge", "Base", "CompteurDebit", "Consultation", "Contenu", "Conversation", "Ecoute", "Enregistrement", "Formulation",
    "Interaction", "Langue", "Marque", "MessageSms", "MessageWhatsapp", "Passage", "PreferenceLangue", "Province", "Rappel",
    "RemonteeRecue", "Signalement", "Territoire", "Traduction",
]
