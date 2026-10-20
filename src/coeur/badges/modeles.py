from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base


class Badge(Base):
    __tablename__ = "badges"
    __table_args__ = {"schema": SCHEMA_COEUR}

    # Empreinte HMAC du numéro normalisé (voir badges.service.empreinte_badge).
    empreinte: Mapped[str] = mapped_column(String(64), primary_key=True)
    territoire_code: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.territoires.code"), index=True
    )
    actif: Mapped[bool] = mapped_column(default=True, server_default="true")
    importe_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
