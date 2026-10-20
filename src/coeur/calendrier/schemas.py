from datetime import date

from pydantic import BaseModel


class PeriodeSortie(BaseModel):
    date_debut: date
    date_fin: date


class CalendrierSortie(BaseModel):
    territoire_code: str
    territoire_nom: str
    # Vide : dates pas encore publiées pour ce territoire.
    passages: list[PeriodeSortie]
