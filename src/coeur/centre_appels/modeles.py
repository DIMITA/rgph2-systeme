from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base

STATUTS_RAPPEL = ("a_rappeler", "en_cours", "rappele", "injoignable", "expire")
# Issue d'un appel, notée par l'agent (aucun texte libre : pas de donnée personnelle).
QUALIFICATIONS = ("renseigne", "signalement", "transmis_bcr", "hors_sujet", "coupe")


class Appel(Base):
    """Déroulement d'un appel au numéro vert. Le numéro n'est gardé que sous forme d'empreinte."""

    __tablename__ = "appels"
    __table_args__ = (
        CheckConstraint(f"qualification IN {QUALIFICATIONS}", name="qualification"),
        {"schema": SCHEMA_COEUR},
    )

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
    qualification: Mapped[str | None] = mapped_column(String(20))


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


class Ecoute(Base):
    """Journal des écoutes d'enregistrements : qui a écouté quoi, et quand.

    Il survit à la suppression de l'enregistrement (preuve en cas de contestation)
    et n'est effacé qu'à la purge de fin de conservation.
    """

    __tablename__ = "ecoutes"
    __table_args__ = {"schema": SCHEMA_COEUR}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enregistrement_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.enregistrements.id", ondelete="SET NULL"), index=True
    )
    fichier: Mapped[str] = mapped_column(String(255))
    utilisateur: Mapped[str] = mapped_column(String(255))
    ecoute_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
