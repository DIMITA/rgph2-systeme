"""Importe tous les modèles pour que les migrations les voient."""

from coeur.base import Base
from coeur.connaissances.modeles import Contenu, Formulation, Langue, Traduction
from coeur.interactions.modeles import Interaction
from coeur.signalements.modeles import Signalement
from coeur.territoires.modeles import Province, Territoire

__all__ = [
    "Base", "Contenu", "Formulation", "Interaction", "Langue", "Province",
    "Signalement", "Territoire", "Traduction",
]
