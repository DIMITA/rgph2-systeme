from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from coeur.commun import SchemaEntree
from coeur.confidentialite.service import normaliser_telephone

TypeSignalement = Literal["menage_non_visite", "rumeur", "agent_douteux", "autre"]
StatutSignalement = Literal["nouveau", "en_traitement", "clos"]


class SignalementEntree(SchemaEntree):
    type: TypeSignalement
    territoire_code: str = Field(max_length=16)
    localite: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    telephone: str | None = Field(default=None, max_length=20)

    @field_validator("telephone")
    @classmethod
    def _telephone_valide(cls, valeur: str | None) -> str | None:
        if valeur is not None:
            normaliser_telephone(valeur)
        return valeur


class SignalementCree(BaseModel):
    id: int
    statut: StatutSignalement


class SignalementSortie(BaseModel):
    """Vue Ministère. Ni numéro, ni empreinte."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    horodatage: datetime
    canal: str
    type: TypeSignalement
    territoire_code: str
    localite: str | None
    description: str | None
    statut: StatutSignalement


class ChangementStatut(SchemaEntree):
    statut: StatutSignalement
