from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base

SERVICES = ("passage", "badge")
RESULTATS = ("trouve", "non_publie", "valide", "retire", "inconnu")
SENS_SMS = ("entrant", "sortant")
STATUTS_SMS = ("recu", "envoye", "echec", "plafond")


class PreferenceLangue(Base):
    """Langue choisie par un usager, pour ne pas la redemander à chaque session.

    L'USSD rejoue chaque session depuis son premier écran (voir ussd/moteur.py) : il
    doit savoir quelle langue était connue *au début* de la session. D'où la session
    USSD du dernier changement et la langue d'avant (vide : premier contact).
    """

    __tablename__ = "preferences_langue"
    __table_args__ = {"schema": SCHEMA_COEUR}

    usager_empreinte: Mapped[str] = mapped_column(String(64), primary_key=True)
    langue: Mapped[str] = mapped_column(String(8))
    session_ussd: Mapped[str | None] = mapped_column(String(100))
    langue_avant: Mapped[str | None] = mapped_column(String(8))
    maj_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Consultation(Base):
    """Usage d'un service hors FAQ (date de passage, badge), pour les statistiques."""

    __tablename__ = "consultations"
    __table_args__ = (
        CheckConstraint(f"service IN {SERVICES}", name="service"),
        CheckConstraint(f"resultat IN {RESULTATS}", name="resultat"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    canal: Mapped[str] = mapped_column(String(20))
    service: Mapped[str] = mapped_column(String(10))
    resultat: Mapped[str] = mapped_column(String(12))
    langue: Mapped[str] = mapped_column(String(8))
    # Territoire consulté, ou territoire d'affectation d'un badge valide.
    territoire_code: Mapped[str | None] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.territoires.code"), index=True
    )
    usager_empreinte: Mapped[str | None] = mapped_column(String(64))


class MessageSms(Base):
    """Journal des SMS reçus et envoyés : ni texte, ni numéro. Sert au plafond et aux coûts."""

    __tablename__ = "sms"
    __table_args__ = (
        CheckConstraint(f"sens IN {SENS_SMS}", name="sens"),
        CheckConstraint(f"statut IN {STATUTS_SMS}", name="statut"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    sens: Mapped[str] = mapped_column(String(8))
    usager_empreinte: Mapped[str] = mapped_column(String(64), index=True)
    segments: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    statut: Mapped[str] = mapped_column(String(8))
