from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base


class Province(Base):
    __tablename__ = "provinces"
    __table_args__ = {"schema": SCHEMA_COEUR}

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    nom: Mapped[str] = mapped_column(String(100))


class Territoire(Base):
    """Territoire administratif ou ville. Aucune statistique n'est produite en dessous."""

    __tablename__ = "territoires"
    __table_args__ = (
        CheckConstraint("type IN ('territoire', 'ville')", name="type"),
        {"schema": SCHEMA_COEUR},
    )

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    nom: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(16))
    province_code: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.provinces.code"), index=True
    )
