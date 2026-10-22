from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base


class Reglage(Base):
    """Un réglage du cœur, chiffré avec CLE_MAITRE. Le nom est celui du champ de
    `coeur.config.Parametres` (pepper_telephone, numero_vert…)."""

    __tablename__ = "reglages"
    __table_args__ = {"schema": SCHEMA_COEUR}

    cle: Mapped[str] = mapped_column(String(64), primary_key=True)
    valeur: Mapped[str] = mapped_column(Text)
    modifie_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
