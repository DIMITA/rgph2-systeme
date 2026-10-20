from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, SmallInteger, String, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base

TYPES = ("menage_non_visite", "rumeur", "agent_douteux", "autre")
STATUTS = ("nouveau", "en_traitement", "clos")


class Signalement(Base):
    __tablename__ = "signalements"
    __table_args__ = (
        CheckConstraint(f"type IN {TYPES}", name="type"),
        CheckConstraint(f"statut IN {STATUTS}", name="statut"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Clé aléatoire secrète (0-255) pour la perturbation des statistiques
    # (statistiques.service.perturber). Jamais exposée.
    cle_cellule: Mapped[int] = mapped_column(
        SmallInteger, server_default=text("floor(random() * 256)::smallint")
    )
    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    canal: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(20))
    territoire_code: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.territoires.code"), index=True
    )
    # Quartier ou village, pour que les équipes de terrain puissent agir.
    # N'est jamais utilisé dans les statistiques.
    localite: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500))
    usager_empreinte: Mapped[str | None] = mapped_column(String(64))
    statut: Mapped[str] = mapped_column(String(16), server_default="nouveau")
