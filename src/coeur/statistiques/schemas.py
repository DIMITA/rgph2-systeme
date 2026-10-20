from datetime import date
from enum import StrEnum

from pydantic import BaseModel


class Niveau(StrEnum):
    """Mailles autorisées. Il n'en existe volontairement aucune plus fine que le territoire."""

    NATIONAL = "national"
    PROVINCE = "province"
    TERRITOIRE = "territoire"


class LigneInteractions(BaseModel):
    unite: str
    canal: str
    langue: str
    # None = valeur masquée (secret statistique).
    nb_interactions: int | None
    nb_escalades: int | None
    nb_usagers_uniques: int | None
    masque: bool


class LigneSignalements(BaseModel):
    unite: str
    type: str
    nb_signalements: int | None
    masque: bool


class StatistiquesSortie(BaseModel):
    niveau: Niveau
    depuis: date | None
    jusqu_a: date | None
    seuil_secret: int
    interactions: list[LigneInteractions]
    signalements: list[LigneSignalements]
