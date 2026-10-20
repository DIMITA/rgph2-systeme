"""Table du calendrier (schéma public : administrée dans Directus, lue par l'API)."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import Base
from coeur.connaissances.modeles import _CONTRAINTE_STATUT


class Passage(Base):
    """Période de passage des agents dans un territoire. Servie seulement si « publie ».

    Le territoire est un code du référentiel (schéma coeur, invisible pour Directus) :
    pas de clé étrangère, l'API ignore les codes inconnus.
    """

    __tablename__ = "calendrier_passages"
    __table_args__ = (
        CheckConstraint(_CONTRAINTE_STATUT, name="statut"),
        CheckConstraint("date_fin >= date_debut", name="dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    territoire_code: Mapped[str] = mapped_column(String(16), index=True)
    date_debut: Mapped[date] = mapped_column(Date)
    date_fin: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(16), default="brouillon", server_default="brouillon")
    date_maj: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
