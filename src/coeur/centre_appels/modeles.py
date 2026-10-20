from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base

STATUTS_RAPPEL = ("a_rappeler", "rappele", "injoignable", "expire")


class Appel(Base):
    """Déroulement d'un appel au numéro vert. Le numéro n'est gardé que sous forme d'empreinte."""

    __tablename__ = "appels"
    __table_args__ = {"schema": SCHEMA_COEUR}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Identifiant de l'appel dans Asterisk (linkedid).
    reference: Mapped[str] = mapped_column(String(64), unique=True)
    debut: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    langue: Mapped[str | None] = mapped_column(String(8))
    usager_empreinte: Mapped[str | None] = mapped_column(String(64))
    entree_file_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decroche_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    poste: Mapped[str | None] = mapped_column(String(32))
    fin_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rappel_demande: Mapped[bool] = mapped_column(default=False, server_default="false")


class Rappel(Base):
    """Demande de rappel. Seule donnée où le numéro est conservé, chiffré, le temps du rappel."""

    __tablename__ = "rappels"
    __table_args__ = (
        CheckConstraint(f"statut IN {STATUTS_RAPPEL}", name="statut"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cree_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    appel_reference: Mapped[str] = mapped_column(String(64))
    # Numéro chiffré (Fernet). Effacé dès que le rappel est traité ou expiré.
    numero_chiffre: Mapped[str | None] = mapped_column(Text)
    langue: Mapped[str | None] = mapped_column(String(8))
    statut: Mapped[str] = mapped_column(String(16), server_default="a_rappeler")
    traite_a: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    traite_par: Mapped[str | None] = mapped_column(String(255))


class Enregistrement(Base):
    """Conversation enregistrée (fichier dans DOSSIER_ENREGISTREMENTS)."""

    __tablename__ = "enregistrements"
    __table_args__ = {"schema": SCHEMA_COEUR}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cree_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    appel_reference: Mapped[str] = mapped_column(String(64), index=True)
    fichier: Mapped[str] = mapped_column(String(255), unique=True)
    poste: Mapped[str | None] = mapped_column(String(32))
