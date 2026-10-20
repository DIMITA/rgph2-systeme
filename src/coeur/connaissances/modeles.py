"""Tables des contenus éditoriaux (schéma public, le seul visible par Directus).

Elles sont créées par les migrations (le schéma est versionné dans le dépôt),
remplies et validées dans Directus, et lues par l'API avec un rôle en lecture seule.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from coeur.base import Base

STATUTS = ("brouillon", "en_revue", "publie", "archive")
STATUT_PUBLIE = "publie"
_CONTRAINTE_STATUT = "statut IN ('brouillon', 'en_revue', 'publie', 'archive')"


class Langue(Base):
    __tablename__ = "langues"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    nom: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(default=True, server_default="true")


class Contenu(Base):
    """Un sujet de la FAQ (ex. « calendrier de passage »), indépendant de la langue."""

    __tablename__ = "contenus"
    __table_args__ = (
        CheckConstraint(_CONTRAINTE_STATUT, name="statut"),
        CheckConstraint("ordre_svi BETWEEN 1 AND 8", name="ordre_svi"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cle: Mapped[str] = mapped_column(String(100), unique=True)
    categorie: Mapped[str] = mapped_column(String(50), default="general", server_default="general")
    statut: Mapped[str] = mapped_column(String(16), default="brouillon", server_default="brouillon")
    # Position dans le menu téléphonique (1 à 8). Vide : absent du serveur vocal.
    ordre_svi: Mapped[int | None]
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    date_maj: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Traduction(Base):
    """Texte d'un contenu dans une langue. Chaque langue est validée séparément."""

    __tablename__ = "contenus_traductions"
    __table_args__ = (
        CheckConstraint(_CONTRAINTE_STATUT, name="statut"),
        CheckConstraint("char_length(reponse_courte) <= 160", name="reponse_courte_160"),
        UniqueConstraint("contenu_id", "langue_code", name="uq_contenus_traductions_contenu_langue"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contenu_id: Mapped[int] = mapped_column(
        ForeignKey("contenus.id", ondelete="CASCADE"), index=True
    )
    langue_code: Mapped[str] = mapped_column(ForeignKey("langues.code"))
    question: Mapped[str] = mapped_column(Text)
    reponse: Mapped[str] = mapped_column(Text)
    # Version de 160 caractères au plus, pour l'USSD et le SMS.
    reponse_courte: Mapped[str | None] = mapped_column(String(160))
    # Fichier audio enregistré par un locuteur natif.
    audio_url: Mapped[str | None] = mapped_column(String(500))
    # Question enregistrée, annoncée dans le menu du serveur vocal.
    audio_question_url: Mapped[str | None] = mapped_column(String(500))
    statut: Mapped[str] = mapped_column(String(16), default="brouillon", server_default="brouillon")
    date_maj: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Formulation(Base):
    """Autre façon de poser la question, pour aider la recherche (ex. « date de passage »)."""

    __tablename__ = "formulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    contenu_id: Mapped[int] = mapped_column(
        ForeignKey("contenus.id", ondelete="CASCADE"), index=True
    )
    langue_code: Mapped[str] = mapped_column(ForeignKey("langues.code"))
    texte: Mapped[str] = mapped_column(String(300))
