"""Importe tous les modèles pour que les migrations les voient."""

from coeur.base import Base
from coeur.centre_appels.modeles import Appel, Enregistrement, Rappel
from coeur.connaissances.modeles import Contenu, Formulation, Langue, Traduction
from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement
from coeur.territoires.modeles import Province, Territoire

__all__ = [
    "Appel", "Base", "Contenu", "Enregistrement", "Formulation", "Interaction", "Langue",
    "Province", "Rappel", "Signalement", "Territoire", "Traduction",
]
