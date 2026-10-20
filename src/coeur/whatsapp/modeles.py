from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import SCHEMA_COEUR, Base

SENS = ("entrant", "sortant")
# « service » : réponse dans les 24 h suivant un message du citoyen (gratuite) ;
# « modele » : message pré-approuvé par Meta, envoyé hors de cette fenêtre (facturé).
CATEGORIES = ("service", "modele")
STATUTS = ("recu", "envoye", "echec")


class Conversation(Base):
    """Où en est un usager quand une réponse libre est attendue (badge, quartier).

    Rien d'autre n'est gardé : ni messages, ni numéro. Une attente de plus de
    WHATSAPP_ATTENTE_MINUTES est oubliée, et la ligne disparaît à la purge.
    """

    __tablename__ = "conversations_whatsapp"
    __table_args__ = {"schema": SCHEMA_COEUR}

    usager_empreinte: Mapped[str] = mapped_column(String(64), primary_key=True)
    # « badge », « localite » ou vide.
    attente: Mapped[str | None] = mapped_column(String(20))
    # Choix déjà faits pendant l'attente (code du territoire…), jamais de texte libre.
    contexte: Mapped[dict] = mapped_column(JSON, default=dict)
    maj_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )


class MessageWhatsapp(Base):
    """Journal des messages : ni texte, ni numéro. Sert aux statistiques et aux coûts."""

    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        CheckConstraint(f"sens IN {SENS}", name="sens"),
        CheckConstraint(f"categorie IN {CATEGORIES}", name="categorie"),
        CheckConstraint(f"statut IN {STATUTS}", name="statut"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    horodatage: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    sens: Mapped[str] = mapped_column(String(8))
    usager_empreinte: Mapped[str] = mapped_column(String(64), index=True)
    categorie: Mapped[str] = mapped_column(String(8), default="service", server_default="service")
    statut: Mapped[str] = mapped_column(String(8))


class Abonnement(Base):
    """Rappels de passage demandés par un usager pour un territoire (consentement explicite).

    Seule donnée WhatsApp où le numéro est conservé, chiffré (comme les demandes de
    rappel du centre d'appels), car il faut écrire à l'usager plus tard. L'abonnement
    et son numéro sont effacés au « STOP », ou WHATSAPP_ABONNEMENT_JOURS_APRES jours
    après la fin du dernier passage publié dans le territoire.
    """

    __tablename__ = "abonnements_whatsapp"
    __table_args__ = (
        UniqueConstraint("usager_empreinte", "territoire_code",
                         name="uq_abonnements_whatsapp_usager_territoire"),
        {"schema": SCHEMA_COEUR},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usager_empreinte: Mapped[str] = mapped_column(String(64), index=True)
    numero_chiffre: Mapped[str] = mapped_column(Text)
    territoire_code: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA_COEUR}.territoires.code"), index=True
    )
    langue: Mapped[str] = mapped_column(String(8))
    cree_a: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Rappels déjà envoyés, ex. ["12:j3", "12:veille"] (identifiant de la période, étape).
    envoyes: Mapped[list] = mapped_column(JSON, default=list)
