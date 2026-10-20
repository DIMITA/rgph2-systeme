from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base


class Interaction(Base):
    """Une question posée par un canal. Aucun nom, aucun numéro en clair."""

    __tablename__ = "interactions"
    __table_args__ = (
        CheckConstraint("resultat IN ('reponse', 'escalade')", name="resultat"),
        CheckConstraint("entree IN ('texte', 'voix')", name="entree"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    canal: Mapped[str] = mapped_column(String(20))
    langue_demandee: Mapped[str] = mapped_column(String(8))
    langue_servie: Mapped[str | None] = mapped_column(String(8))
    territoire_code: Mapped[str | None] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.territoires.code"), index=True
    )
    # Empreinte HMAC du numéro (voir coeur.confidentialite).
    usager_empreinte: Mapped[str | None] = mapped_column(String(64))
    resultat: Mapped[str] = mapped_column(String(10))
    # Question écrite ou dite (message vocal transcrit) : la qualité se mesure à part.
    entree: Mapped[str] = mapped_column(String(8), server_default="texte")
    motif_escalade: Mapped[str | None] = mapped_column(String(40))
    # Pas de clé étrangère : l'historique reste lisible si un contenu est supprimé du CMS.
    contenu_id: Mapped[int | None]
    score: Mapped[float]
    # Question de l'usager, numéros et courriels masqués. Sert à enrichir la FAQ.
    # None selon CONSERVATION_TEXTE_QUESTIONS.
    texte_masque: Mapped[str | None] = mapped_column(String(500))
