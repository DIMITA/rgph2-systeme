from pydantic import BaseModel, Field

from coeur.badges.service import StatutBadge
from coeur.commun import SchemaEntree


class BadgeEntree(SchemaEntree):
    numero: str = Field(min_length=1, max_length=40)
    # Sert seulement à limiter les essais et à compter les usagers ; jamais enregistré.
    telephone: str | None = Field(default=None, max_length=20)


class BadgeSortie(BaseModel):
    statut: StatutBadge
    territoire_code: str | None
    territoire_nom: str | None
